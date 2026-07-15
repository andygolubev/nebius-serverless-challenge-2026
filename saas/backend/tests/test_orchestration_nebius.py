"""Nebius orchestration backend: submission building, state mapping, failure
paths, and the S3 artifact reader — all against fakes, no SDK or live S3.
"""

from __future__ import annotations

import io
import json

import pytest

from app.artifacts import S3ArtifactReader
from app.models import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_STARTING,
    STATUS_TRAINING,
    ArtifactManifest,
    Job,
)
from app.nebius_client import shell_join_args
from app.orchestration import (
    MockBackend,
    NebiusBackend,
    REMOTE_SUBMISSION_ERROR,
    build_backend,
    map_nebius_state,
    parse_duration_seconds,
    sanitize_error,
)
from app.settings import NebiusSettings, SettingsError
from app.store import JobStore

SETTINGS = NebiusSettings(
    project_id="project-e00test",
    subnet_id="vpcsubnet-e00test",
    job_image="cr.example/sim2policy:sb3-runtime",
    mjx_job_image="cr.example/sim2policy:mjx-runtime",
    s3_secret_selector="mbsec-artifacts/latest",
    aws_access_key_id="AKIATEST",
    aws_secret_access_key="topsecretvalue",
    s3_endpoint_url="https://storage.eu-north1.nebius.cloud",
    s3_region="eu-north1",
    s3_bucket="sim2policy-artifacts",
    registry_secret="mbsec-registry/1",
)


def _job(**overrides) -> Job:
    defaults = dict(
        id="a" * 32,
        tenant_id="user@example.com",
        preset="go1-mjx-quick",
        environment="go1",
        algorithm="ppo-mjx",
        resolved_config={
            "environment": "go1",
            "algorithm": "ppo-mjx",
            "params": {"total_timesteps": 5_000_000, "learning_rate": 3e-4, "seed": 7},
        },
        status=STATUS_QUEUED,
        created_at="2026-07-11T00:00:00+00:00",
        updated_at="2026-07-11T00:00:00+00:00",
    )
    defaults.update(overrides)
    return Job(**defaults)


class FakeJobsClient:
    def __init__(
        self, states=("PROVISIONING", "RUNNING", "COMPLETED"), fail_create=None
    ):
        self.states = list(states)
        self.fail_create = fail_create
        self.submissions = []

    def create_job(self, submission) -> str:
        if self.fail_create is not None:
            raise self.fail_create
        self.submissions.append(submission)
        return "aijob-e00fake"

    def get_job_state(self, job_id: str) -> str:
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


class FakeArtifactReader:
    def __init__(self, manifest=None):
        self.manifest = manifest

    def read_manifest(self, job_id, run_id):
        return self.manifest


class SequenceArtifactReader:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def read_manifest(self, job_id, run_id):
        value = self.values.pop(0) if len(self.values) > 1 else self.values[0]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return value


def _backend(client=None, reader=None) -> NebiusBackend:
    return NebiusBackend(
        SETTINGS,
        client or FakeJobsClient(),
        reader or FakeArtifactReader(),
        poll_interval=0,
    )


# -- backend selection --


def test_build_backend_mock_default():
    assert isinstance(build_backend("mock"), MockBackend)


def test_build_backend_unknown():
    with pytest.raises(ValueError):
        build_backend("bogus")


def test_build_backend_nebius_fails_fast_without_config(monkeypatch):
    for name in ("NEBIUS_PROJECT_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SettingsError):
        build_backend("nebius")


def test_settings_reports_all_missing_vars():
    with pytest.raises(SettingsError) as e:
        NebiusSettings.from_env(env={})
    assert "NEBIUS_PROJECT_ID" in str(e.value)
    assert "AWS_SECRET_ACCESS_KEY" in str(e.value)


# -- submission building --


def test_submission_derives_from_catalog_only():
    sub = _backend().build_submission(_job())
    assert sub.name == f"sim2policy-{'a' * 32}"
    assert sub.image == SETTINGS.mjx_job_image
    assert sub.command == "python"
    assert sub.args[:2] == ["-m", "sim2policy.hosted_mjx"]
    assert "configs/go1_mjx.yaml" in sub.args
    joined = " ".join(sub.args)
    assert "training.total_steps=5000000" in joined
    # learning_rate is not an allowed override path; it must never reach the args
    assert "learning_rate" not in joined
    assert "seed=7" in joined
    assert "storage.bucket=sim2policy-artifacts" in joined
    assert sub.platform == "gpu-h100-sxm"
    assert sub.preset == "1gpu-16vcpu-200gb"
    assert sub.timeout_seconds == 4 * 3600
    assert sub.parent_id == SETTINGS.project_id


def test_mjx_submission_uses_mjx_image_and_h100():
    job = _job(
        preset="go1-mjx-demo",
        environment="go1",
        algorithm="ppo-mjx",
        resolved_config={
            "environment": "go1",
            "algorithm": "ppo-mjx",
            "params": {"total_timesteps": 500_000, "seed": 7},
        },
    )
    sub = _backend().build_submission(job)
    assert sub.image == SETTINGS.mjx_job_image
    assert sub.args[:2] == ["-m", "sim2policy.hosted_mjx"]
    assert "configs/go1_mjx.yaml" in sub.args
    assert sub.platform == "gpu-h100-sxm"
    assert sub.preset == "1gpu-16vcpu-200gb"


def test_settings_require_mjx_job_image():
    env = {
        "NEBIUS_PROJECT_ID": "p",
        "NEBIUS_SUBNET_ID": "s",
        "SIM2POLICY_JOB_IMAGE": "img",
        "NEBIUS_S3_SECRET_SELECTOR": "sel",
        "AWS_ACCESS_KEY_ID": "k",
        "AWS_SECRET_ACCESS_KEY": "sk",
        "AWS_ENDPOINT_URL_S3": "https://s3",
        "AWS_DEFAULT_REGION": "r",
        "SIM2POLICY_S3_BUCKET": "b",
    }
    with pytest.raises(SettingsError) as e:
        NebiusSettings.from_env(env=env)
    assert "SIM2POLICY_MJX_JOB_IMAGE" in str(e.value)
    env["SIM2POLICY_MJX_JOB_IMAGE"] = "mjx-img"
    assert NebiusSettings.from_env(env=env).mjx_job_image == "mjx-img"


def test_submission_never_contains_plaintext_secret():
    sub = _backend().build_submission(_job())
    assert sub.env == {
        "AWS_ACCESS_KEY_ID": "AKIATEST",
        "SIM2POLICY_RUNTIME_IMAGE": SETTINGS.mjx_job_image,
    }
    assert sub.env_secrets == {"AWS_SECRET_ACCESS_KEY": SETTINGS.s3_secret_selector}
    assert SETTINGS.aws_secret_access_key not in " ".join(sub.args)


def test_nebius_argument_join_preserves_structured_server_owned_value():
    args = [
        "-m",
        "sim2policy.hosted_mjx",
        "--set",
        'training.hyperparameters={"entropy_cost":0.005,"policy_obs_key":"state"}',
    ]

    import shlex

    assert shlex.split(shell_join_args(args)) == args


def test_unsafe_run_id_refused():
    backend, store = _backend(), JobStore()
    job = _job(id="../evil")
    store.put(job)
    backend._run(job, store)
    assert store.get(job.tenant_id, job.id).status == STATUS_FAILED


def test_combination_without_job_spec_fails():
    backend, store = _backend(), JobStore()
    job = _job(
        environment="ant",
        algorithm="ppo-mjx",
        resolved_config={"environment": "ant", "algorithm": "ppo-mjx", "params": {}},
    )
    store.put(job)
    backend._run(job, store)
    stored = store.get(job.tenant_id, job.id)
    assert stored.status == STATUS_FAILED
    assert "not available" in stored.error


def test_step_cap_enforced():
    job = _job()
    job.resolved_config["params"]["total_timesteps"] = 999_000_000
    with pytest.raises(ValueError, match="cap"):
        _backend().build_submission(job)


# -- lifecycle --


def test_happy_path_records_id_and_completes():
    manifest_reader = FakeArtifactReader(
        manifest=ArtifactManifest(job_id="a" * 32, status=STATUS_COMPLETED)
    )
    client = FakeJobsClient(
        states=(
            "PROVISIONING",
            "RUNNING",
            "COMPLETED",
        )
    )
    backend, store = _backend(client, manifest_reader), JobStore()
    job = _job()
    store.put(job)
    backend._run(job, store)
    stored = store.get(job.tenant_id, job.id)
    assert stored.nebius_job_id == "aijob-e00fake"
    assert stored.status == STATUS_COMPLETED
    assert store.get_artifacts(job.id) is not None


def test_remote_success_waits_for_delayed_manifest():
    manifest = ArtifactManifest(job_id="a" * 32, status=STATUS_COMPLETED)
    reader = SequenceArtifactReader(
        [None, RuntimeError("temporary S3 failure"), manifest]
    )
    backend = NebiusBackend(
        SETTINGS,
        FakeJobsClient(states=("COMPLETED",)),
        reader,
        poll_interval=0,
        finalize_attempts=4,
    )
    store, job = JobStore(), _job()
    store.put(job)
    backend._run(job, store)
    stored = store.get(job.tenant_id, job.id)
    assert reader.calls == 3
    assert stored.status == STATUS_COMPLETED
    assert stored.artifacts_status == "ready"


def test_finalization_timeout_is_terminal_and_sanitized():
    backend = NebiusBackend(
        SETTINGS,
        FakeJobsClient(states=("COMPLETED",)),
        FakeArtifactReader(None),
        poll_interval=0,
        finalize_attempts=2,
    )
    store, job = JobStore(), _job()
    store.put(job)
    backend._run(job, store)
    stored = store.get(job.tenant_id, job.id)
    assert stored.status == STATUS_FAILED
    assert stored.failure_phase == "finalization"
    assert "timeout" in stored.error


def test_active_job_guard_prevents_duplicate_reconciler():
    backend = NebiusBackend(
        SETTINGS, FakeJobsClient(), FakeArtifactReader(None), poll_interval=0
    )
    job = _job(nebius_job_id="aijob-existing", status=STATUS_STARTING)
    import threading

    release = threading.Event()
    assert backend._start(job, release.wait)
    assert not backend._start(job, release.wait)
    release.set()


def test_remote_failure_marks_job_failed():
    client = FakeJobsClient(states=("RUNNING", "FAILED"))
    backend, store = _backend(client), JobStore()
    job = _job()
    store.put(job)
    backend._run(job, store)
    assert store.get(job.tenant_id, job.id).status == STATUS_FAILED


def test_create_failure_is_sanitized():
    boom = RuntimeError(
        "denied for key topsecretvalue; request_id=internal-request; "
        "trace_id=internal-trace\nstack frame 1"
    )
    backend, store = _backend(FakeJobsClient(fail_create=boom)), JobStore()
    job = _job()
    store.put(job)
    backend._run(job, store)
    stored = store.get(job.tenant_id, job.id)
    assert stored.status == STATUS_FAILED
    assert stored.error == REMOTE_SUBMISSION_ERROR


# -- state mapping / helpers --


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PROVISIONING", STATUS_STARTING),
        ("STARTING", STATUS_STARTING),
        ("RUNNING", STATUS_TRAINING),
        ("JOB_STATE_RUNNING", STATUS_TRAINING),
        ("COMPLETED", STATUS_COMPLETED),
        ("FAILED", STATUS_FAILED),
        ("CANCELLED", STATUS_FAILED),
        ("ERROR", STATUS_FAILED),
        ("STATE_UNSPECIFIED", None),
        ("CANCELLING", None),
    ],
)
def test_map_nebius_state(raw, expected):
    assert map_nebius_state(raw) == expected


@pytest.mark.parametrize(
    ("raw", "seconds"), [("1h", 3600), ("2h30m", 9000), ("45m", 2700), ("90s", 90)]
)
def test_parse_duration(raw, seconds):
    assert parse_duration_seconds(raw) == seconds


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        parse_duration_seconds("soon")


def test_sanitize_error_truncates_and_redacts():
    msg = sanitize_error(RuntimeError("x" * 500), secrets=("x" * 500,))
    assert len(msg) <= 200


# -- S3 artifact reader (fixtures, no live S3) --


class NoSuchKey(Exception):
    pass


class StubS3:
    def __init__(self, objects: dict[str, dict]):
        self.objects = objects

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise NoSuchKey(Key)
        return {"Body": io.BytesIO(json.dumps(self.objects[Key]).encode())}


RUN = "b" * 32
PREFIX = f"sim2policy/{RUN}"


def test_reader_returns_none_without_manifest():
    reader = S3ArtifactReader(StubS3({}), "sim2policy-artifacts")
    assert reader.read_manifest("job1", RUN) is None


def test_reader_builds_manifest_from_fixtures():
    stub = StubS3(
        {
            f"{PREFIX}/report/artifacts.json": {
                "artifacts": {
                    "final_policy": "checkpoints/final.zip",
                    "metrics_json": "report/metrics.json",
                    "video_final": "videos/final.mp4",
                    "progression_montage": "videos/progression_montage.mp4",
                }
            },
            f"{PREFIX}/report/metrics.json": {"mean_reward": 987.6, "steps": 100000},
            f"{PREFIX}/metadata/status.json": {"run_id": RUN, "status": "completed"},
        }
    )
    manifest = S3ArtifactReader(stub, "sim2policy-artifacts").read_manifest("job1", RUN)
    assert manifest.job_id == "job1"
    assert manifest.status == "completed"
    assert manifest.metrics["mean_reward"] == 987.6
    assert manifest.media == sorted(
        [f"{PREFIX}/videos/final.mp4", f"{PREFIX}/videos/progression_montage.mp4"]
    )


def test_reader_tolerates_missing_metrics_and_status():
    stub = StubS3(
        {f"{PREFIX}/report/artifacts.json": {"final_policy": "checkpoints/final.zip"}}
    )
    manifest = S3ArtifactReader(stub, "sim2policy-artifacts").read_manifest("job1", RUN)
    assert manifest.status == "completed"
    assert manifest.metrics == {}
    assert manifest.media == []
