from __future__ import annotations

import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.artifacts import S3ArtifactReader
from app.custom_storage import CustomRobotStorage, CustomStorageError
from app.custom_training import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    SCHEMA_VERSION,
    TRAINING_PROFILE_VERSION,
    canonical_json,
)
from app.models import Job, PreparationAttempt
from app.orchestration import NebiusBackend, REMOTE_SUBMISSION_ERROR
from app.settings import CustomTrainingSettings, NebiusSettings
from app.store import CustomTrainingStore, JobStore


NEBIUS = NebiusSettings(
    project_id="project-test",
    subnet_id="subnet-test",
    mjx_job_image="registry.example/mjx@sha256:" + "b" * 64,
    s3_secret_selector="secret/version",
    aws_access_key_id="access-id",
    aws_secret_access_key="never-in-submission",
    s3_endpoint_url="https://storage.example",
    s3_region="eu-north1",
    s3_bucket="artifacts",
    registry_secret="registry/version",
)
CUSTOM = CustomTrainingSettings(
    enabled=True,
    runtime_image="registry.example/sb3@sha256:" + "a" * 64,
    max_active_preparations_per_tenant=1,
    max_active_training_jobs_per_tenant=1,
    max_daily_starts_per_tenant=8,
    preparation_finalize_attempts=3,
    feature_revision="custom-robot-v1",
)


class S3:
    def __init__(self, *, omit_metadata: bool = False) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.fail_head: str | None = None
        self.omit_metadata = omit_metadata

    def put_object(self, *, Bucket, Key, Body, Metadata, **_kwargs):
        assert Bucket == "artifacts"
        self.objects[Key] = (bytes(Body), Metadata)

    def head_object(self, *, Bucket, Key):
        assert Bucket == "artifacts"
        if Key == self.fail_head:
            raise RuntimeError("head failure with tenant data")
        body, metadata = self.objects[Key]
        return {
            "ContentLength": len(body),
            "Metadata": {} if self.omit_metadata else metadata,
        }

    def delete_object(self, *, Bucket, Key):
        assert Bucket == "artifacts"
        self.objects.pop(Key, None)

    def get_object(self, *, Bucket, Key):
        assert Bucket == "artifacts"
        if Key not in self.objects:
            error = RuntimeError("missing")
            error.response = {"Error": {"Code": "NoSuchKey"}}  # type: ignore[attr-defined]
            raise error
        body, _ = self.objects[Key]
        return {"Body": io.BytesIO(body), "ContentLength": len(body)}


def _attempt() -> PreparationAttempt:
    return PreparationAttempt(
        id="prepare-one",
        tenant_id="tenant@example.com",
        setup_id="setup-one",
        robot_id="robot-one",
        fingerprint="f" * 64,
        state="queued",
        phase="queued",
        created_at="2026-07-14T00:00:00+00:00",
        updated_at="2026-07-14T00:00:00+00:00",
        runtime_image_digest=CUSTOM.runtime_image,
        adapter_version=ADAPTER_VERSION,
        reward_version=REWARD_VERSION,
        profile_version=PREPARATION_PROFILE_VERSION,
    )


def _job() -> Job:
    return Job(
        id="run-one",
        tenant_id="tenant@example.com",
        environment="uploaded-biped",
        algorithm="ppo-sb3",
        resolved_config={
            "job_kind": "custom-robot",
            "backend": "sb3",
            "profile": "custom-ppo-quick",
            "runtime": {"image_digest": CUSTOM.runtime_image},
            "training": {"version": TRAINING_PROFILE_VERSION},
        },
        status="queued",
        created_at="2026-07-14T00:00:00+00:00",
        updated_at="2026-07-14T00:00:00+00:00",
        job_kind="custom-robot",
    )


def _backend(storage=None) -> NebiusBackend:
    return NebiusBackend(
        NEBIUS,
        object(),
        object(),
        custom_settings=CUSTOM,
        custom_storage=storage,
    )


class CompletedJobs:
    def create_job(self, _submission) -> str:
        return "aijob-prepare-test"

    def get_job_state(self, _job_id: str) -> str:
        return "COMPLETED"


class FailingJobs:
    def create_job(self, _submission) -> str:
        raise RuntimeError("/tenant/private.xml secret provider payload")


class ReportStorage:
    def __init__(self, report) -> None:
        self.report = report

    def read_preparation_report(self, _preparation_id: str):
        if isinstance(self.report, Exception):
            raise self.report
        return self.report


def test_custom_submissions_are_fixed_typed_cpu_jobs() -> None:
    training = _backend().build_submission(_job())
    preparation = _backend().build_preparation_submission(_attempt())
    assert training.image == preparation.image == CUSTOM.runtime_image
    assert (training.platform, training.preset, training.disk_gib) == (
        "cpu-d3",
        "16vcpu-64gb",
        100,
    )
    assert (preparation.platform, preparation.preset, preparation.disk_gib) == (
        "cpu-d3",
        "4vcpu-16gb",
        50,
    )
    assert training.args == [
        "-m",
        "sim2policy.custom_robot_job",
        "train",
        "--identity",
        "run-one",
    ]
    assert preparation.args[-2:] == ["--identity", "prepare-one"]
    serialized = json.dumps(training.__dict__)
    assert "tenant@example.com" not in serialized
    assert NEBIUS.aws_secret_access_key not in serialized
    assert training.env_secrets == {"AWS_SECRET_ACCESS_KEY": NEBIUS.s3_secret_selector}


def test_custom_submission_rejects_mixed_profile_and_runtime() -> None:
    job = _job()
    job.resolved_config["training"]["version"] = "tenant-profile"  # type: ignore[index]
    with pytest.raises(ValueError, match="profile"):
        _backend().build_submission(job)
    attempt = _attempt().model_copy(update={"runtime_image_digest": "tenant-image"})
    with pytest.raises(ValueError, match="provenance"):
        _backend().build_preparation_submission(attempt)


def test_storage_uses_fixed_prefixes_verifies_size_and_cleans_partial_objects() -> None:
    client = S3()
    storage = CustomRobotStorage(client, "artifacts")
    storage.publish_preparation_inputs(
        "prepare-one", robot=b"<mujoco/>", setup=b"{}", manifest=b"{}"
    )
    assert set(client.objects) == {
        "sim2policy/preparations/prepare-one/inputs/robot.xml",
        "sim2policy/preparations/prepare-one/inputs/normalized-setup.json",
        "sim2policy/preparations/prepare-one/inputs/input-manifest.json",
    }
    failed_client = S3()
    failed_client.fail_head = (
        "sim2policy/preparations/prepare-two/inputs/normalized-setup.json"
    )
    with pytest.raises(CustomStorageError, match="publication"):
        CustomRobotStorage(failed_client, "artifacts").publish_preparation_inputs(
            "prepare-two", robot=b"<mujoco/>", setup=b"{}", manifest=b"{}"
        )
    assert failed_client.objects == {}


def test_storage_streams_bounded_inputs_when_object_metadata_is_omitted() -> None:
    client = S3(omit_metadata=True)
    storage = CustomRobotStorage(client, "artifacts")
    storage.publish_preparation_inputs(
        "prepare-no-metadata", robot=b"<mujoco/>", setup=b"{}", manifest=b"{}"
    )
    assert len(client.objects) == 3


def test_preparation_report_requires_content_hash() -> None:
    client = S3()
    storage = CustomRobotStorage(client, "artifacts")
    report = {
        "schema_version": SCHEMA_VERSION,
        "preparation_id": "prepare-one",
        "fingerprint": "f" * 64,
        "status": "accepted",
        "failure_phase": None,
        "failure_reason": None,
        "phases": [],
        "compiled": {},
        "schemas": {},
        "versions": {},
    }
    report["report_sha256"] = hashlib.sha256(canonical_json(report)).hexdigest()
    key = "sim2policy/preparations/prepare-one/report/preparation.json"
    raw = canonical_json(report)
    client.objects[key] = (raw, {"sha256": hashlib.sha256(raw).hexdigest()})
    assert storage.read_preparation_report("prepare-one") == report
    tampered_report = dict(report)
    tampered_report["report_sha256"] = "0" * 64
    client.objects[key] = (canonical_json(tampered_report), {})
    with pytest.raises(CustomStorageError, match="digest"):
        storage.read_preparation_report("prepare-one")


def test_custom_artifact_manifest_requires_every_matching_object_checksum() -> None:
    client = S3()
    paths = {
        "final_policy": "checkpoints/final.zip",
        "metrics_json": "report/metrics.json",
        "report_md": "report/report.md",
        "reward_curve": "report/reward-curve.png",
        "video_final": "videos/final.mp4",
        "resolved_config": "report/resolved-config.json",
        "runtime_versions": "report/runtime-versions.json",
        "policy_bundle": "bundle/policy-bundle.zip",
        "bundle_manifest": "bundle/manifest.json",
        "robot_xml": "inputs/robot.xml",
        "normalized_setup": "inputs/normalized-setup.json",
    }
    checksums = {}
    for name, relative in paths.items():
        body = (
            canonical_json({"simulator_only": True})
            if name == "metrics_json"
            else f"artifact:{name}".encode()
        )
        digest = hashlib.sha256(body).hexdigest()
        client.objects[f"sim2policy/run-one/{relative}"] = (body, {"sha256": digest})
        checksums[name] = {"sha256": digest, "size_bytes": len(body)}
    for relative, document in (
        ("metadata/status.json", {"status": "completed"}),
        ("report/artifacts.json", {"artifacts": paths, "checksums": checksums}),
    ):
        body = canonical_json(document)
        client.objects[f"sim2policy/run-one/{relative}"] = (
            body,
            {"sha256": hashlib.sha256(body).hexdigest()},
        )

    manifest = S3ArtifactReader(client, "artifacts").read_manifest("job-one", "run-one")
    assert manifest is not None
    assert {artifact.id for artifact in manifest.artifacts} == set(paths)

    client.objects["sim2policy/run-one/videos/final.mp4"] = (
        b"tampered",
        {"sha256": "0" * 64},
    )
    with pytest.raises(ValueError, match="checksum"):
        S3ArtifactReader(client, "artifacts").read_manifest("job-one", "run-one")

    artifacts_document = json.loads(
        client.objects["sim2policy/run-one/report/artifacts.json"][0]
    )
    artifacts_document.pop("checksums")
    body = canonical_json(artifacts_document)
    client.objects["sim2policy/run-one/report/artifacts.json"] = (
        body,
        {"sha256": hashlib.sha256(body).hexdigest()},
    )
    with pytest.raises(ValueError, match="checksum manifest is missing"):
        S3ArtifactReader(client, "artifacts").read_manifest("job-one", "run-one")


def test_preparation_submission_poll_and_report_gate_are_restart_safe(tmp_path) -> None:
    db_path = str(tmp_path / "saas.db")
    store = CustomTrainingStore(db_path)
    attempt, created = store.reserve_preparation(
        _attempt(), max_active_per_tenant=1, retry=False
    )
    assert created is True
    accepted_report = {
        "fingerprint": attempt.fingerprint,
        "status": "accepted",
        "failure_phase": None,
        "failure_reason": None,
        "report_sha256": "1" * 64,
    }
    backend = NebiusBackend(
        NEBIUS,
        CompletedJobs(),
        object(),
        poll_interval=0,
        custom_settings=CUSTOM,
        custom_storage=ReportStorage(accepted_report),
    )
    backend._run_preparation(attempt, store)
    finished = CustomTrainingStore(db_path).get_preparation(
        attempt.tenant_id, attempt.id
    )
    assert finished is not None
    assert finished.state == "accepted"
    assert finished.nebius_job_id == "aijob-prepare-test"
    assert finished.report_ready is True


@pytest.mark.parametrize(
    "report,reason",
    [
        (None, "preparation-report-not-ready"),
        (
            {"fingerprint": "0" * 64, "status": "accepted"},
            "report-fingerprint-mismatch",
        ),
        (RuntimeError("unsafe provider detail"), "preparation-report-not-ready"),
    ],
)
def test_missing_invalid_or_unreadable_preparation_report_fails_safely(
    tmp_path, report, reason: str
) -> None:
    store = CustomTrainingStore(str(tmp_path / "saas.db"))
    attempt, _ = store.reserve_preparation(
        _attempt(), max_active_per_tenant=1, retry=False
    )
    backend = _backend(ReportStorage(report))
    backend.poll_interval = 0
    backend._finalize_preparation(attempt, store)
    failed = store.get_preparation(attempt.tenant_id, attempt.id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.failure_reason == reason
    assert "unsafe provider detail" not in failed.model_dump_json()


def test_custom_training_submission_failure_is_sanitized_in_state_and_logs(
    tmp_path, caplog
) -> None:
    store = JobStore(str(tmp_path / "saas.db"))
    job = _job()
    store.put(job)
    backend = NebiusBackend(
        NEBIUS,
        FailingJobs(),
        object(),
        custom_settings=CUSTOM,
    )
    backend._run(job, store)
    failed = store.get(job.tenant_id, job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == REMOTE_SUBMISSION_ERROR
    assert "/tenant" not in caplog.text
    assert "provider payload" not in caplog.text


def test_cross_connection_double_click_reservations_are_atomic(tmp_path) -> None:
    db_path = str(tmp_path / "saas.db")

    def reserve_preparation(index: int):
        attempt = _attempt().model_copy(update={"id": f"prepare-{index}"})
        return CustomTrainingStore(db_path).reserve_preparation(
            attempt, max_active_per_tenant=1, retry=False
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        preparations = list(executor.map(reserve_preparation, range(2)))
    assert sum(created for _, created in preparations) == 1
    assert len({attempt.id for attempt, _ in preparations}) == 1

    def reserve_training(index: int):
        job = _job().model_copy(update={"id": f"run-{index}"})
        return CustomTrainingStore(db_path).reserve_training_job(
            job,
            setup_id="setup-one",
            idempotency_key="same-start-request",
            max_active_per_tenant=1,
            max_daily_starts=8,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        trainings = list(executor.map(reserve_training, range(2)))
    assert sum(created for _, created in trainings) == 1
    assert len({job.id for job, _ in trainings}) == 1
