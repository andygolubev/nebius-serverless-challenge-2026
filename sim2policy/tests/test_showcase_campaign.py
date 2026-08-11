"""Campaign state machine: idempotency, serialization, resume, and fail-closed stops."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sim2policy.campaign_infra import Probe
from sim2policy.campaign_provider import (
    BlockedProvider,
    JobStatus,
    NebiusCliProvider,
    ProviderError,
    provider_from_environment,
)
from sim2policy.campaign_state import CampaignError, CampaignStore
from sim2policy.execution_location import (
    ExecutionLocationError,
    LocationAttestation,
    require_nebius_execution,
)
from sim2policy.showcase_campaign import (
    EXIT_ACTIVE,
    EXIT_INVARIANT,
    EXIT_NEEDS_HUMAN,
    EXIT_OK,
    EXIT_REJECTED,
    Campaign,
    evidence_reader_factory_from_environment,
)
from sim2policy.showcase_matrix import load_matrix

ROOT = Path(__file__).parents[1]
MATRIX = ROOT / "configs/showcase_training_matrix.yaml"
IMAGE_DIGEST = "sha256:" + "b" * 64


def _attestation() -> LocationAttestation:
    return LocationAttestation(
        schema_version=1,
        provider="nebius",
        resource_id="computeinstance-e00showcasebuilder",
        region="eu-north1",
        immutable_revision="git:" + "a" * 40,
        command_class="campaign",
        started_at="2026-07-26T00:00:00+00:00",
    )


class FakeProvider:
    """Deterministic provider double: records calls, returns scripted states."""

    def __init__(
        self,
        *,
        states: list[str] | None = None,
        submit_error: bool = False,
        existing_name: str | None = None,
        audit_result: dict[str, Any] | None = None,
    ) -> None:
        self.submitted: list[dict[str, Any]] = []
        self._states = states or ["COMPLETED"]
        self._submit_error = submit_error
        self._existing_name = existing_name
        self._audit = audit_result if audit_result is not None else {"active_jobs": [], "running_instances": []}
        self.poll_count = 0

    def submit(self, plan, *, idempotency_key):
        if self._submit_error:
            raise ProviderError("submission response was lost")
        self.submitted.append({"plan": dict(plan), "idempotency_key": idempotency_key})
        return f"aijob-{len(self.submitted)}"

    def poll(self, remote_id):
        state = self._states[min(self.poll_count, len(self._states) - 1)]
        self.poll_count += 1
        from sim2policy.campaign_provider import classify

        return JobStatus(remote_id=remote_id, state=state, terminal=classify(state))

    def find_by_name(self, name):
        if self._existing_name == name:
            return JobStatus(remote_id="aijob-adopted", state="RUNNING", terminal=False)
        return None

    def audit(self):
        return self._audit


class FakeProber:
    """Live-probe double: returns scripted probe results, records what was asked."""

    def __init__(self, *, failing: set[str] | None = None) -> None:
        self.failing = failing or set()
        self.calls: list[dict[str, Any]] = []

    def collect(self, *, expected_revision, hardware=None, expected_branch="main"):
        self.calls.append(
            {
                "expected_revision": expected_revision,
                "hardware": dict(hardware) if hardware else None,
                "expected_branch": expected_branch,
            }
        )
        names = ["repository", "infrastructure", "credentials"]
        if hardware is not None:
            names.append("preset_quota")
        probes = [Probe(name, name not in self.failing, {"stub": True}) for name in names]
        probes.append(
            Probe(
                "github_actions",
                True,
                {"runs": [{"conclusion": "failure"}]},
                informational=True,
            )
        )
        return probes


def test_live_provider_requires_explicit_nebius_dispatch_and_project_scope() -> None:
    assert isinstance(provider_from_environment({}), BlockedProvider)
    assert isinstance(
        provider_from_environment({"SIM2POLICY_PROVIDER_DISPATCH": "nebius"}),
        BlockedProvider,
    )
    assert isinstance(
        provider_from_environment(
            {
                "SIM2POLICY_PROVIDER_DISPATCH": "nebius",
                "SIM2POLICY_NEBIUS_PROJECT_ID": "project-e00wkbbppr00tab5fhhmz7",
            }
        ),
        NebiusCliProvider,
    )

def test_provider_parses_json_after_operation_progress_output() -> None:
    """`job create` narrates the operation on stdout before emitting the resource.

    Reporting that as a failure would abandon a job the provider already created,
    which is how a duplicate submission happens.
    """
    import subprocess as _subprocess

    def runner(command, **_kwargs):
        # Exactly what the CLI writes: terminal control sequences around a
        # progress line, then the resource. `\x1b[2K` must not look like an array.
        stdout = (
            '\x1b[?25l\x1b[2Kwaiting for operation "computeoperation-e00abc" over '
            'resource "aijob-e00xyz" to complete\x1b[1A\x1b[2K\n'
            '{"metadata": {"id": "aijob-e00xyz"}}\n'
        )
        return _subprocess.CompletedProcess(command, 0, stdout, "")

    provider = NebiusCliProvider(project_id="project-e00wkbbppr00tab5fhhmz7", runner=runner)
    remote_id = provider.submit(
        {
            "run_id": "smoke-sb3-1",
            "image_reference": "registry.example/sim2policy@sha256:" + "a" * 64,
            "hardware": {"platform": "cpu-d3", "preset": "8vcpu-32gb", "disk_gib": 100, "timeout_minutes": 60},
            "command": ["python", "-m", "sim2policy.hosted_sb3", "--set", "seed=0"],
        },
        idempotency_key="key",
    )
    assert remote_id == "aijob-e00xyz"


def test_provider_parses_json_followed_by_operation_progress_output() -> None:
    """The narration is not always a prefix; it also lands after the resource.

    A live submission was lost exactly this way: the job existed, the response did
    not parse, and the attempt recorded no remote id.
    """
    import subprocess as _subprocess

    def runner(command, **_kwargs):
        stdout = (
            '{"metadata": {"id": "aijob-e00xyz"}}\n'
            '\x1b[2Koperation "computeoperation-e00abc" over resource '
            '"aijob-e00xyz" completed\n'
        )
        return _subprocess.CompletedProcess(command, 0, stdout, "")

    provider = NebiusCliProvider(project_id="project-e00wkbbppr00tab5fhhmz7", runner=runner)
    remote_id = provider.submit(
        {
            "run_id": "smoke-sb3-1",
            "image_reference": "registry.example/sim2policy@sha256:" + "a" * 64,
            "hardware": {"platform": "cpu-d3", "preset": "8vcpu-32gb", "disk_gib": 100, "timeout_minutes": 60},
            "command": ["python", "-m", "sim2policy.hosted_sb3", "--set", "seed=0"],
        },
        idempotency_key="key",
    )
    assert remote_id == "aijob-e00xyz"


def test_provider_reads_the_remote_id_from_the_plain_text_create_response() -> None:
    """`ai job create` ignores `--format json` and prints a text summary.

    Verbatim from a live submission. Failing to read the ID here leaves a running,
    billing job with no recorded remote id to watch or clean up.
    """
    import subprocess as _subprocess

    def runner(command, **_kwargs):
        stdout = (
            "\nJob ID: aijob-e00my0tag2x84c2f43\n"
            "Job created successfully.\n"
            "Job:\n"
            "  ID:       aijob-e00my0tag2x84c2f43\n"
            "  Name:     smoke-mjx-flat-20260729-01\n"
            "  State:    RUNNING\n"
        )
        return _subprocess.CompletedProcess(command, 0, stdout, "\n")

    provider = NebiusCliProvider(project_id="project-e00wkbbppr00tab5fhhmz7", runner=runner)
    remote_id = provider.submit(
        {
            "run_id": "smoke-mjx-flat-20260729-01",
            "image_reference": "registry.example/sim2policy@sha256:" + "a" * 64,
            "hardware": {"platform": "cpu-d3", "preset": "8vcpu-32gb", "disk_gib": 100, "timeout_minutes": 60},
            "command": ["python", "-m", "sim2policy.hosted_mjx", "--set", "seed=0"],
        },
        idempotency_key="key",
    )
    assert remote_id == "aijob-e00my0tag2x84c2f43"


def test_provider_submit_uses_the_real_job_create_surface() -> None:
    """Flags are checked against the CLI that exists, not the one we wish existed."""
    import subprocess as _subprocess

    captured: list[list[str]] = []

    def runner(command, **_kwargs):
        captured.append(list(command))
        return _subprocess.CompletedProcess(command, 0, '{"metadata": {"id": "aijob-e1"}}', "")

    provider = NebiusCliProvider(project_id="project-e00wkbbppr00tab5fhhmz7", runner=runner)
    provider.submit(
        {
            "run_id": "smoke-sb3-1",
            "image_reference": "registry.example/sim2policy@sha256:" + "a" * 64,
            "hardware": {"platform": "cpu-d3", "preset": "8vcpu-32gb", "disk_gib": 100, "timeout_minutes": 60},
            "command": ["python", "-m", "sim2policy.hosted_sb3", "--set", "seed=0"],
            "subnet_id": "vpcsubnet-e00abc",
            "environment": {"SIM2POLICY_EXECUTION_LOCATION": "nebius"},
            "secret_environment": {"AWS_SECRET_ACCESS_KEY": "mbsecver-e00abc"},
            "registry_secret": "mbsecver-e00reg",
        },
        idempotency_key="key",
    )
    command = captured[0]
    assert command[1:4] == ["ai", "job", "create"]
    for flag in ("--image", "--container-command", "--args", "--platform", "--preset",
                 "--disk-size", "--timeout", "--subnet-id", "--registry-secret"):
        assert flag in command, flag
    # The provider CLI copies the image argument into a 64-character label, so
    # digest pinning stays in the reviewed plan while this boundary submits the
    # pre-verified immutable tag.
    assert command[command.index("--image") + 1] == "registry.example/sim2policy"
    # The container arguments are one joined string, never a shell command line.
    assert command[command.index("--args") + 1] == "-m sim2policy.hosted_sb3 --set seed=0"
    assert "--env-secret" in command
    assert "AWS_SECRET_ACCESS_KEY=mbsecver-e00abc" in command


class FakeEvidence:
    """In-memory curated-run evidence, keyed by run id."""

    def __init__(self, documents: dict[str, dict[str, dict[str, Any]]]) -> None:
        self.documents = documents

    def __call__(self, run_id: str):
        run = self.documents.get(run_id, {})

        class Reader:
            def read_json(_self, relative: str):
                return run.get(relative)

            def head(_self, relative: str):
                return {"size_bytes": 1} if relative else None

        return Reader()


def _complete_metrics(*, matrix_digest: str, preferred: bool = True) -> dict[str, Any]:
    return {
        "matrix_digest": matrix_digest,
        "environment": "Reacher-v5",
        "backend": "sb3",
        "runtime_seconds": 400.0,
        "benchmark": {"estimated_cost": 0.03, "rate_date": "2026-07-26"},
        "success": {"met": True, "criterion": "mean_reward >= -10"},
        "aggregate": {"mean_reward": -6.5, "mean_episode_length": 50.0, "episodes": 20},
        "selected_checkpoint": {
            "effective_step": 800000,
            "native_path": "step-000000800000.zip",
            "sha256": "c" * 64,
        },
        "seed_roles": {"selection": [101, 151, 211, 271, 331], "final": [0, 1, 2, 3, 4]},
        "ranking_explanation": {"kind": "mean_reward", "fields": ["mean_reward"]},
        "acceptance": {
            "hard": {"criteria": {"mean_reward": True}, "passed": True},
            "preferred": {"criteria": {"mean_reward": preferred}, "passed": preferred},
        },
        "episodes": [{"seed": seed, "reward": -6.5, "length": 50} for seed in [0, 1, 2, 3, 4] * 4],
        "progression": [
            {"stage": "untrained", "selected": False, "checkpoint": {"effective_step": 0, "sha256": "d" * 64}},
            {"stage": "mid", "selected": False, "checkpoint": {"effective_step": 250000, "sha256": "f" * 64}},
            {"stage": "selected", "selected": True, "checkpoint": {"effective_step": 800000, "sha256": "c" * 64}},
            {"stage": "final-step", "selected": False, "regression": True, "checkpoint": {"effective_step": 1000000, "sha256": "e" * 64}},
        ],
    }


def _run_documents(run_id: str, matrix_digest: str, *, preferred: bool = True) -> dict[str, dict[str, dict[str, Any]]]:
    metrics = _complete_metrics(matrix_digest=matrix_digest, preferred=preferred)
    artifacts = {
        name: f"path/{name}"
        for name in (
            "final_policy", "metrics_json", "report_md", "resolved_config", "runtime_versions",
            "policy_bundle", "video_untrained", "video_mid", "video_selected", "video_final",
            "video_final_step", "progression_montage",
        )
    }
    return {
        run_id: {
            "report/artifacts.json": {
                "artifacts": artifacts,
                "checksums": {name: {"sha256": "a" * 64, "size_bytes": 1} for name in artifacts},
            },
            "metadata/status.json": {"status": "completed"},
            "report/metrics.json": metrics,
            "report/resolved-config.json": {
                "gallery_example_id": "reacher-target",
                "runtime_image": f"registry.example/sim2policy-sb3@{IMAGE_DIGEST}",
            },
            "report/runtime-versions.json": {"mujoco": "3.3.7"},
        }
    }


def _campaign_fixture(tmp_path: Path, campaign_id: str):
    """Build an initialized campaign whose implementation gate has passed."""
    matrix = load_matrix(MATRIX)
    store = CampaignStore(tmp_path, campaign_id)

    def build(provider=None, evidence=None, environment_extra=None, **kwargs):
        kwargs.setdefault("prober", FakeProber())
        instance = Campaign(
            store,
            matrix,
            provider=provider or FakeProvider(),
            evidence_reader_factory=evidence,
            sleeper=lambda _s: None,
            environment={
                "SIM2POLICY_IMMUTABLE_REVISION": "git:" + "a" * 40,
                "SIM2POLICY_BRANCH": "main",
                "SIM2POLICY_ARTIFACT_BUCKET": "sim2policy-artifacts",
                "SIM2POLICY_ARTIFACT_ENDPOINT": "https://storage.eu-north1.nebius.cloud",
                "SIM2POLICY_ARTIFACT_REGION": "eu-north1",
                "SIM2POLICY_ARTIFACT_ACCESS_KEY_ID": "NAKIEXAMPLEKEYID0000",
                "SIM2POLICY_SUBNET_ID": "vpcsubnet-e00re7tmw1apqd4pmm",
                "NEBIUS_ARTIFACT_SECRET_VERSION": "mbsecver-e00artifact",
                "NEBIUS_REGISTRY_SECRET_VERSION": "mbsecver-e00registry",
                **(environment_extra or {}),
            },
            **kwargs,
        )
        return instance

    instance = build()
    instance.initialize(_attestation())
    for name in (
        "nebius-quality-gates.json", "sb3-image.json", "mjx-image.json",
        "sb3-smoke.json", "mjx-smoke.json", "cloud-audit.json",
    ):
        payload: dict[str, Any] = {"provider": "nebius", "region": "eu-north1"}
        if name.endswith("-image.json"):
            runtime = name.split("-")[0]
            payload |= {
                "tag": f"registry.example/sim2policy-{runtime}:{runtime}-{'a' * 40}",
                "digest": IMAGE_DIGEST,
            }
        store.write_json(store.evidence_path(name), payload)
    instance.implementation_gate()
    return build, store, matrix


@pytest.fixture()
def campaign(tmp_path: Path):
    return _campaign_fixture(tmp_path, "gallery-result-20260726")


@pytest.fixture()
def g1_campaign(tmp_path: Path):
    return _campaign_fixture(tmp_path, "gallery-g1-survival-20260811-01")


# -- init and idempotency ---------------------------------------------------


def test_init_is_idempotent_and_refuses_a_different_matrix_digest(tmp_path: Path, campaign) -> None:
    build, store, matrix = campaign
    code, envelope = build().initialize(_attestation())
    assert code == EXIT_OK and envelope["decision"] == "ALREADY_INITIALIZED"

    class Drifted:
        normalized = dict(matrix.normalized)
        digest = "0" * 64

        def card(self, name):
            return matrix.card(name)

        @property
        def campaign(self):
            return matrix.campaign

    code, envelope = Campaign(store, Drifted(), provider=FakeProvider()).initialize(_attestation())
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "MATRIX_DIGEST_MISMATCH"


def test_init_records_ordered_examples_and_a_nebius_attestation(campaign) -> None:
    _build, store, matrix = campaign
    state = store.read()
    assert state["ordered_examples"][0] == "reacher"
    assert state["ordered_examples"][-1] == "g1"
    assert state["matrix_digest"] == matrix.digest
    assert state["location_attestation"]["provider"] == "nebius"
    assert store.evidence_path("init-location.json").is_file()


# -- implementation gate ----------------------------------------------------


def test_implementation_gate_blocks_until_every_nebius_evidence_file_exists(tmp_path: Path) -> None:
    store = CampaignStore(tmp_path, "gallery-result-empty")
    instance = Campaign(store, load_matrix(MATRIX), provider=FakeProvider())
    instance.initialize(_attestation())
    code, envelope = instance.implementation_gate()
    assert code == EXIT_NEEDS_HUMAN
    assert envelope["reason_code"] == "IMPLEMENTATION_EVIDENCE_MISSING"
    assert "sb3-image.json" in envelope["missing_evidence"]


def test_implementation_gate_refuses_evidence_produced_off_nebius(tmp_path: Path, campaign) -> None:
    """A GitHub-hosted runner's success is informational, never a preparation gate."""
    _build, store, _matrix = campaign
    store.write_json(
        store.evidence_path("sb3-smoke.json"), {"provider": "github-actions", "region": "eu-north1"}
    )
    instance = Campaign(store, load_matrix(MATRIX), provider=FakeProvider())
    code, envelope = instance.implementation_gate()
    assert code == EXIT_INVARIANT
    assert envelope["reason_code"] == "EXECUTION_LOCATION_INVALID"


# -- plan and submit --------------------------------------------------------


def test_plan_is_reviewable_and_names_everything_the_runbook_requires(campaign) -> None:
    build, _store, matrix = campaign
    code, envelope = build().plan("reacher", 0)
    assert code == EXIT_OK
    plan = envelope["plan"]
    assert plan["run_id"] == "showcase-gallery-result-20260726-reacher-s0"
    assert plan["durable_prefix"] == "sim2policy/showcase-gallery-result-20260726-reacher-s0/"
    assert plan["matrix_digest"] == matrix.digest
    assert plan["image_digest"] == IMAGE_DIGEST
    assert plan["effective_steps"] == 1_000_000
    assert plan["checkpoint_every_steps"] == 100_000
    assert plan["hardware"]["preemptible"] is False
    assert plan["seed_roles"]["selection"] == [101, 151, 211, 271, 331]
    assert plan["seed_roles"]["final"] == [0, 1, 2, 3, 4]
    assert "--set" in plan["command"] and "training.total_steps=1000000" in plan["command"]
    assert envelope["next_command"].startswith("submit --example reacher --seed 0 --confirm-plan-digest")


def test_g1_plan_declares_both_exact_phase_evidence_prefixes(g1_campaign) -> None:
    build, *_ = g1_campaign
    plan = build().build_plan("g1", 0)
    run_id = "showcase-gallery-g1-survival-20260811-01-g1-s0"
    assert plan["run_id"] == run_id
    assert plan["evidence_run_ids"] == [f"{run_id}-rough", f"{run_id}-flat"]
    assert plan["durable_prefix"] == f"sim2policy/{run_id}-rough/"
    assert plan["durable_prefixes"] == [
        f"sim2policy/{run_id}-rough/",
        f"sim2policy/{run_id}-flat/",
    ]
    recovery = plan["g1_recovery"]
    assert recovery["flat_effective_steps"] == 199_229_440
    assert recovery["pilot"]["effective_steps"] == 46_202_880
    assert recovery["full"]["timeout_minutes"] == 300
    assert recovery["full"]["rough_effective_steps"] == 250_511_360
    assert recovery["authorization"]["mode"] == "user_reviewed_survival_v1"
    assert recovery["authorization"]["campaign_id"] == "gallery-g1-survival-20260811-01"
    assert recovery["authorization"]["allowed_jobs"] == 1
    assert recovery["authorization"]["retries_allowed"] == 0
    assert recovery["authorization"]["source_revision"] == "git:" + "a" * 40
    assert recovery["authorization"]["image_digest"] == IMAGE_DIGEST
    assert recovery["authorization"]["matrix_digest"] == plan["matrix_digest"]
    assert "pilot_acceptance" not in recovery
    assert plan["max_retries_remaining"] == 0


def test_g1_full_plan_is_blocked_for_any_other_campaign(campaign) -> None:
    build, *_ = campaign
    with pytest.raises(CampaignError, match="different campaign"):
        build().build_plan("g1", 0)


def test_g1_direct_full_rejects_mutable_revision_or_image_binding(g1_campaign) -> None:
    build, store, _ = g1_campaign
    with pytest.raises(CampaignError, match="immutable revision or image"):
        build(environment_extra={"SIM2POLICY_IMMUTABLE_REVISION": "git:not-a-sha"}).build_plan("g1", 0)

    store.write_json(
        store.evidence_path("mjx-image.json"),
        {"provider": "nebius", "region": "eu-north1", "tag": "registry.example/mjx:latest", "digest": IMAGE_DIGEST},
    )
    with pytest.raises(CampaignError, match="immutable revision or image"):
        build().build_plan("g1", 0)


def test_plan_refuses_a_seed_the_matrix_does_not_declare(campaign) -> None:
    build, *_ = campaign
    with pytest.raises(CampaignError, match="not declared"):
        build().build_plan("reacher", 999)


def test_submit_requires_the_exact_confirmed_plan_digest(campaign) -> None:
    build, *_ = campaign
    instance = build()
    instance.plan("reacher", 0)
    code, envelope = instance.submit("reacher", 0, "not-the-digest")
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "PLAN_DIGEST_MISMATCH"


def test_submit_records_a_remote_id_and_is_idempotent(campaign) -> None:
    build, _store, _matrix = campaign
    provider = FakeProvider()
    instance = build(provider=provider)
    _code, planned = instance.plan("reacher", 0)
    digest = planned["plan"]["plan_digest"]

    code, envelope = instance.submit("reacher", 0, digest)
    assert code == EXIT_OK and envelope["remote_id"] == "aijob-1"

    # Re-running the same command never submits twice.
    code, envelope = instance.submit("reacher", 0, digest)
    assert code == EXIT_ACTIVE and envelope["decision"] == "ALREADY_SUBMITTED"
    assert len(provider.submitted) == 1


def test_submit_passes_only_secret_selectors_never_values(campaign) -> None:
    build, store, _matrix = campaign
    provider = FakeProvider()
    instance = Campaign(
        store,
        load_matrix(MATRIX),
        provider=provider,
        environment={
            "SIM2POLICY_IMMUTABLE_REVISION": "git:" + "a" * 40,
            "SIM2POLICY_ARTIFACT_BUCKET": "sim2policy-artifacts",
            "SIM2POLICY_ARTIFACT_ENDPOINT": "https://storage.eu-north1.nebius.cloud",
            "SIM2POLICY_ARTIFACT_REGION": "eu-north1",
            "SIM2POLICY_ARTIFACT_ACCESS_KEY_ID": "NAKIEXAMPLEKEYID0000",
            "SIM2POLICY_SUBNET_ID": "vpcsubnet-e00re7tmw1apqd4pmm",
            "NEBIUS_ARTIFACT_SECRET_VERSION": "mbsecver-e00artifact",
            "NEBIUS_REGISTRY_SECRET_VERSION": "mbsecver-e00abc",
            "NEBIUS_REGISTRY_PASSWORD": "SENTINEL-VALUE-must-not-appear",
        },
    )
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    submitted = json.dumps(provider.submitted[0], sort_keys=True)
    assert "mbsecver-e00abc" in submitted
    assert "SENTINEL-VALUE-must-not-appear" not in submitted


def test_a_second_submission_while_a_job_is_active_is_refused(campaign) -> None:
    build, *_ = campaign
    instance = build()
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    _code, other = instance.plan("reacher", 7)
    code, envelope = instance.submit("reacher", 7, other["plan"]["plan_digest"])
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "ACTIVE_JOB_PRESENT"


def test_a_lost_submission_response_adopts_the_matching_remote_job(campaign) -> None:
    """Recovery depends on the run name being deterministic, not randomized."""
    build, *_ = campaign
    run_name = "showcase-gallery-result-20260726-reacher-s0"
    provider = FakeProvider(submit_error=True, existing_name=run_name)
    instance = build(provider=provider)
    _code, planned = instance.plan("reacher", 0)
    code, envelope = instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    assert code == EXIT_OK and envelope["remote_id"] == "aijob-adopted"


def test_a_lost_submission_with_no_matching_job_stops_for_a_human(campaign) -> None:
    build, *_ = campaign
    instance = build(provider=FakeProvider(submit_error=True, existing_name="some-other-name"))
    _code, planned = instance.plan("reacher", 0)
    code, envelope = instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    assert code == EXIT_NEEDS_HUMAN and envelope["reason_code"] == "SUBMIT_FAILED"


def test_a_submission_that_never_created_a_job_can_be_replanned(campaign) -> None:
    """A failure that spent nothing must not cost the whole campaign ID."""
    build, *_ = campaign
    instance = build(provider=FakeProvider(submit_error=True, existing_name="some-other-name"))
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])

    code, envelope = instance.plan("reacher", 0)
    assert code == EXIT_OK and envelope["decision"] == "PLAN_READY"
    assert envelope["state"] == "PLANNED"


def test_a_needs_human_attempt_holding_a_remote_job_is_not_replanned(campaign) -> None:
    """The block only lifts for attempts with no remote job to reconcile."""
    build, *_ = campaign
    instance = build(provider=FakeProvider(states=["WOBBLING"]))
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    instance.watch(poll_seconds=0)

    code, envelope = instance.plan("reacher", 0)
    assert code == EXIT_OK and envelope["decision"] == "ALREADY_PLANNED"


# -- watch ------------------------------------------------------------------


def test_watch_reports_active_then_terminal(campaign) -> None:
    build, *_ = campaign
    provider = FakeProvider(states=["RUNNING", "RUNNING", "COMPLETED"])
    instance = build(provider=provider)
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])

    code, envelope = instance.watch(poll_seconds=0)
    assert code == EXIT_ACTIVE and envelope["decision"] == "ACTIVE"

    code, envelope = instance.watch(poll_seconds=0, until_terminal=True)
    assert code == EXIT_OK and envelope["decision"] == "TERMINAL"
    assert envelope["next_command"].startswith("verify --example reacher")


def test_an_unclassified_provider_state_is_never_guessed(campaign) -> None:
    build, *_ = campaign
    instance = build(provider=FakeProvider(states=["WOBBLING"]))
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    code, envelope = instance.watch(poll_seconds=0)
    assert code == EXIT_NEEDS_HUMAN and envelope["reason_code"] == "UNKNOWN_PROVIDER_STATE"


def test_watch_with_no_active_job_is_a_safe_no_op(campaign) -> None:
    build, *_ = campaign
    code, envelope = build().watch(poll_seconds=0)
    assert code == EXIT_OK and envelope["decision"] == "NO_ACTIVE_JOB"


# -- verify -----------------------------------------------------------------


def _submitted_and_terminal(
    build,
    run_id: str,
    matrix,
    *,
    preferred: bool = True,
    documents=None,
    environment_extra=None,
    states: list[str] | None = None,
):
    provider = FakeProvider(states=states or ["COMPLETED"])
    evidence = FakeEvidence(documents or _run_documents(run_id, matrix.digest, preferred=preferred))
    instance = build(provider=provider, evidence=evidence, environment_extra=environment_extra)
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    instance.watch(poll_seconds=0, until_terminal=True)
    return instance


def _all_base_seeds_verified(build, matrix, *, preferred: bool = True, prefix: str = "showcase-gallery-result-20260726-reacher"):
    """Every declared base seed run and verified — what `select` requires.

    Selection ranks a complete set by contract: an extension may only follow the
    quality decision taken after all three base seeds.
    """
    seeds = matrix.card("reacher")["seeds"]
    documents: dict = {}
    for seed in seeds:
        documents.update(_run_documents(f"{prefix}-s{seed}", matrix.digest, preferred=preferred))
    instance = build(provider=FakeProvider(states=["COMPLETED"]), evidence=FakeEvidence(documents))
    for seed in seeds:
        _code, planned = instance.plan("reacher", seed)
        instance.submit("reacher", seed, planned["plan"]["plan_digest"])
        instance.watch(poll_seconds=0, until_terminal=True)
        instance.verify("reacher", seed)
    return instance


def test_verify_accepts_a_complete_prefix_and_is_idempotent(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix)
    code, envelope = instance.verify("reacher", 0)
    assert code == EXIT_OK, envelope.get("verification")
    assert envelope["decision"] == "VERIFIED"

    code, envelope = instance.verify("reacher", 0)
    assert code == EXIT_OK and envelope["decision"] == "ALREADY_VERIFIED"


def test_verify_recovers_complete_g1_rough_evidence_after_provider_failure(g1_campaign) -> None:
    """A finalized hard-gate rejection is not a container crash.

    The G1 hosted entry point historically returned campaign exit 20 after it
    uploaded a complete rough result, so the provider recorded FAILED. Exact
    child-prefix evidence is sufficient to recover that old attempt without
    retraining or accepting the rejected policy.
    """
    build, store, matrix = g1_campaign
    job_run_id = "showcase-gallery-g1-survival-20260811-01-g1-s0"
    evidence_run_id = f"{job_run_id}-rough"
    instance = build(
        provider=FakeProvider(states=["FAILED"]),
        evidence=FakeEvidence(_run_documents(evidence_run_id, matrix.digest)),
    )
    _code, planned = instance.plan("g1", 0)
    instance.submit("g1", 0, planned["plan"]["plan_digest"])
    instance.watch(poll_seconds=0, until_terminal=True)

    code, envelope = instance.verify("g1", 0)
    assert code == EXIT_OK
    assert envelope["decision"] == "VERIFIED"
    assert envelope["reason_code"] == "EVIDENCE_COMPLETE_AFTER_PROVIDER_FAILURE"
    persisted = store.read()["attempts"]["g1:0:base"]
    assert persisted["evidence_run_id"] == evidence_run_id
    assert persisted["provider_failure_recovery"]["provider_terminal_state"] == "FAILED"


def test_verify_resolves_the_terminal_state_when_watch_was_interrupted(campaign) -> None:
    """An interrupted watch must not make a completed run look like a failure."""
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    provider = FakeProvider(states=["COMPLETED"])
    evidence = FakeEvidence(_run_documents(run_id, matrix.digest))
    instance = build(provider=provider, evidence=evidence)
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    # No watch ran, so nothing recorded a terminal state.
    assert "provider_terminal_state" not in store.read()["attempts"]["reacher:0:base"]

    code, envelope = instance.verify("reacher", 0)
    assert code == EXIT_OK and envelope["decision"] == "VERIFIED"


def test_a_stopped_attempt_can_be_verified_once_its_blocker_is_resolved(campaign) -> None:
    """NEEDS_HUMAN is a stop, not a grave — but only proof clears it."""
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    provider = FakeProvider(states=["COMPLETED"])
    documents = _run_documents(run_id, matrix.digest)
    instance = build(provider=provider, evidence=FakeEvidence({}))
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    instance.watch(poll_seconds=0, until_terminal=True)
    code, _envelope = instance.verify("reacher", 0)
    assert code == EXIT_REJECTED
    assert store.read()["attempts"]["reacher:0:base"]["state"] == "NEEDS_HUMAN"

    resolved = build(provider=provider, evidence=FakeEvidence(documents))
    code, envelope = resolved.verify("reacher", 0)
    assert code == EXIT_OK and envelope["decision"] == "VERIFIED"


def test_verify_recovers_only_complete_evidence_after_heartbeat_cancellation(campaign) -> None:
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    documents = _run_documents(run_id, matrix.digest)
    provider = FakeProvider(states=["CANCELLED"])
    instance = build(provider=provider, evidence=FakeEvidence(documents))
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    state = store.read()
    attempt = state["attempts"]["reacher:0:base"]
    attempt["state"] = "NEEDS_HUMAN"
    attempt["reason_code"] = "HEARTBEAT_LOST"
    store.write(state)
    code, envelope = instance.verify("reacher", 0)
    assert code == EXIT_OK
    assert envelope["reason_code"] == "EVIDENCE_COMPLETE_AFTER_CANCELLATION"
    persisted = store.read()["attempts"]["reacher:0:base"]
    assert persisted["cancellation_recovery"]["prior_stop_reason"] == "HEARTBEAT_LOST"


def test_verify_never_recovers_an_ordinary_cancelled_job(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(
        build, run_id, matrix, documents=_run_documents(run_id, matrix), states=["CANCELLED"]
    )
    code, envelope = instance.verify("reacher", 0)
    assert code == EXIT_REJECTED
    assert envelope["state"] == "NEEDS_HUMAN"
    assert envelope["reason_code"] != "EVIDENCE_COMPLETE_AFTER_CANCELLATION"


def test_verify_refuses_while_the_job_is_still_active(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    provider = FakeProvider(states=["RUNNING"])
    evidence = FakeEvidence(_run_documents(run_id, matrix.digest))
    instance = build(provider=provider, evidence=evidence)
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])

    code, envelope = instance.verify("reacher", 0)
    assert code == EXIT_ACTIVE and envelope["reason_code"] == "JOB_STILL_ACTIVE"
    assert envelope["next_command"] == "watch --until-terminal"


def test_verify_classifies_a_finalization_only_failure(campaign) -> None:
    """Training evidence durable, artifacts incomplete: retry finalization, not training."""
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    documents = _run_documents(run_id, matrix.digest)
    manifest = documents[run_id]["report/artifacts.json"]
    manifest["artifacts"].pop("policy_bundle")
    manifest["checksums"].pop("policy_bundle")
    instance = _submitted_and_terminal(build, run_id, matrix, documents=documents)
    code, envelope = instance.verify("reacher", 0)
    assert code == EXIT_REJECTED
    assert envelope["reason_code"] == "FINALIZATION_ONLY_FAILURE"


def test_verify_rejects_a_matrix_digest_from_another_campaign(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    documents = _run_documents(run_id, "9" * 64)
    instance = _submitted_and_terminal(build, run_id, matrix, documents=documents)
    code, envelope = instance.verify("reacher", 0)
    assert code == EXIT_REJECTED
    assert any("matrix digest" in item for item in envelope["verification"]["failures"])


# -- cleanup, select, accept ------------------------------------------------


def test_cleanup_blocks_on_an_unaccounted_resource(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix)
    instance.verify("reacher", 0)
    instance.provider = FakeProvider(
        audit_result={"active_jobs": ["aijob-someone-elses"], "running_instances": []}
    )
    code, envelope = instance.cleanup()
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "UNACCOUNTED_RESOURCE"


def test_cleanup_accounts_for_a_declared_sibling_campaigns_job(campaign) -> None:
    """Campaigns run side by side on separate machines; each is serial internally.

    A sibling's job is accounted for. Without this, whichever campaign finished an
    attempt first would call the other's job unaccounted and stop them both.
    """
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(
        build,
        run_id,
        matrix,
        environment_extra={"SIM2POLICY_PARALLEL_CAMPAIGN_IDS": "gallery-go1-01,gallery-g1-01"},
    )
    instance.verify("reacher", 0)
    instance.provider = FakeProvider(
        audit_result={
            "active_jobs": ["aijob-sibling"],
            "active_job_names": {"aijob-sibling": "showcase-gallery-go1-01-go1-s0"},
            "running_instances": [],
        }
    )
    code, envelope = instance.cleanup()
    assert code == EXIT_OK and envelope["reason_code"] == "CLEANUP_PASS"


def test_a_stray_job_is_still_unaccounted_when_siblings_are_declared(campaign) -> None:
    """Tolerating siblings must not blind the audit to a genuinely stray job."""
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(
        build,
        run_id,
        matrix,
        environment_extra={"SIM2POLICY_PARALLEL_CAMPAIGN_IDS": "gallery-go1-01"},
    )
    instance.verify("reacher", 0)
    instance.provider = FakeProvider(
        audit_result={
            "active_jobs": ["aijob-stray"],
            "active_job_names": {"aijob-stray": "someone-elses-experiment"},
            "running_instances": [],
        }
    )
    code, envelope = instance.cleanup()
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "UNACCOUNTED_RESOURCE"
    assert envelope["unaccounted_jobs"] == ["aijob-stray"]


def test_audit_cloud_still_requires_this_campaigns_own_job_to_be_stopped(campaign) -> None:
    """A sibling may run; our own active job means our cleanup is not finished."""
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(
        build,
        run_id,
        matrix,
        environment_extra={"SIM2POLICY_PARALLEL_CAMPAIGN_IDS": "gallery-go1-01"},
    )
    instance.verify("reacher", 0)
    own = store.read()["attempts"]["reacher:0:base"]["remote_id"]
    instance.provider = FakeProvider(
        audit_result={
            "active_jobs": [own, "aijob-sibling"],
            "active_job_names": {
                own: "showcase-gallery-result-20260726-reacher-s0",
                "aijob-sibling": "showcase-gallery-go1-01-go1-s0",
            },
            "running_instances": [],
        }
    )
    code, envelope = instance.audit_cloud()
    assert code == EXIT_INVARIANT and envelope["decision"] == "UNACCOUNTED_RESOURCE"
    assert envelope["own_active_jobs"] == [own]
    assert envelope["unaccounted_jobs"] == []


def test_the_cli_builds_an_evidence_reader_from_the_configured_destination() -> None:
    """`verify` on the orchestration VM needs a real reader, not a test double."""
    assert evidence_reader_factory_from_environment({}) is None
    factory = evidence_reader_factory_from_environment(
        {
            "SIM2POLICY_ARTIFACT_BUCKET": "sim2policy-artifacts",
            "SIM2POLICY_ARTIFACT_ENDPOINT": "https://storage.eu-north1.nebius.cloud",
            "SIM2POLICY_ARTIFACT_REGION": "eu-north1",
        }
    )
    assert factory is not None
    reader = factory("showcase-gallery-result-20260726-reacher-s0")
    assert hasattr(reader, "read_json") and hasattr(reader, "head")


def test_cleanup_blocks_on_an_undeclared_running_instance(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix)
    instance.verify("reacher", 0)
    instance.provider = FakeProvider(
        audit_result={"active_jobs": [], "running_instances": ["computeinstance-stranger"]}
    )
    code, envelope = instance.cleanup()
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "UNACCOUNTED_RESOURCE"
    assert envelope["unaccounted_instances"] == ["computeinstance-stranger"]


def test_cleanup_accounts_for_the_orchestration_vm_and_declared_infrastructure(campaign) -> None:
    """The controller's own VM is always running; demanding zero never passes."""
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(
        build,
        run_id,
        matrix,
        environment_extra={
            "SIM2POLICY_NEBIUS_RESOURCE_ID": "computeinstance-orchestrator",
            "SIM2POLICY_EXPECTED_RUNNING_INSTANCES": "computeinstance-saas",
        },
    )
    instance.verify("reacher", 0)
    instance.provider = FakeProvider(
        audit_result={
            "active_jobs": [],
            "running_instances": ["computeinstance-orchestrator", "computeinstance-saas"],
        }
    )
    code, envelope = instance.cleanup()
    assert code == EXIT_OK and envelope["decision"] == "CLEANED"


def test_cleanup_passes_and_closes_the_attempt(campaign) -> None:
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix)
    instance.verify("reacher", 0)
    code, envelope = instance.cleanup()
    assert code == EXIT_OK and envelope["decision"] == "CLEANED"
    assert store.read()["attempts"]["reacher:0:base"]["state"] == "CLEANED"


def test_select_refuses_until_every_declared_base_seed_is_settled(campaign) -> None:
    """Ranking a partial set could crown an unrepresentative winner."""
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix)
    instance.verify("reacher", 0)
    code, envelope = instance.select("reacher")
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "BASE_SEEDS_INCOMPLETE"
    assert envelope["outstanding_seeds"] == [7, 42]


def test_select_records_the_winner_and_skips_the_extension_when_quality_is_met(campaign) -> None:
    build, _store, matrix = campaign
    instance = _all_base_seeds_verified(build, matrix)
    code, envelope = instance.select("reacher")
    assert code == EXIT_OK
    assert envelope["decision"] == "EXTENSION_SKIPPED_QUALITY_MET"
    assert envelope["selection"]["checkpoint_sha256"] == "c" * 64
    assert envelope["next_command"] == "accept --example reacher"


def test_select_requires_an_extension_when_the_preferred_target_is_missed(campaign) -> None:
    build, _store, matrix = campaign
    instance = _all_base_seeds_verified(build, matrix, preferred=False)
    code, envelope = instance.select("reacher")
    assert code == EXIT_OK and envelope["decision"] == "EXTENSION_REQUIRED"
    assert "--phase extension" in envelope["next_command"]


def test_accept_needs_a_human_when_only_the_hard_floor_passes(campaign) -> None:
    build, _store, matrix = campaign
    instance = _all_base_seeds_verified(build, matrix, preferred=False)
    instance.cleanup()
    instance.select("reacher")
    code, envelope = instance.accept("reacher")
    assert code == EXIT_NEEDS_HUMAN
    assert envelope["reason_code"] == "NEEDS_HUMAN_QUALITY_TARGET"


def test_accept_is_pin_ready_only_with_hard_preferred_and_cleanup(campaign) -> None:
    build, _store, matrix = campaign
    instance = _all_base_seeds_verified(build, matrix)

    # Cleanup has not run: acceptance must not be pin-ready yet.
    instance.select("reacher")
    code, envelope = instance.accept("reacher")
    assert code == EXIT_NEEDS_HUMAN and envelope["reason_code"] == "CLEANUP_REQUIRED"

    instance.cleanup()
    code, envelope = instance.accept("reacher")
    assert code == EXIT_OK and envelope["decision"] == "ACCEPTED"
    assert envelope["acceptance"]["hard_gate"] is True
    assert envelope["acceptance"]["preferred_target"] is True


def test_extension_can_only_be_consumed_once(campaign) -> None:
    build, _store, matrix = campaign
    instance = _all_base_seeds_verified(build, matrix, preferred=False)
    instance.select("reacher")
    plan = instance.build_plan("reacher", 0, phase="extension")
    code, _envelope = instance.extend("reacher", plan["plan_digest"])
    assert code == EXIT_OK
    code, envelope = instance.extend("reacher", plan["plan_digest"])
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "EXTENSION_ALREADY_CONSUMED"


# -- resume, locking, and recovery -----------------------------------------


def test_a_new_process_resumes_from_persisted_state_alone(campaign) -> None:
    """The next command is derived from disk, never from in-process memory."""
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    first = _submitted_and_terminal(build, run_id, matrix)
    first.verify("reacher", 0)

    fresh_store = CampaignStore(store.root.parent, "gallery-result-20260726")
    resumed = Campaign(fresh_store, load_matrix(MATRIX), provider=FakeProvider())
    code, envelope = resumed.status()
    assert code == EXIT_OK
    assert envelope["attempts"]["reacher:0:base"]["state"] == "VERIFIED"


def test_a_held_lock_refuses_a_concurrent_command(campaign) -> None:
    build, store, _matrix = campaign
    instance = build()
    with store.lock("plan"), pytest.raises(CampaignError, match="lock is held"):
        instance.plan("reacher", 0)


def test_recover_lock_refuses_while_the_holder_is_live(campaign) -> None:
    build, store, _matrix = campaign
    instance = build()
    with store.lock("watch"):
        code, envelope = instance.recover_lock()
    assert code == EXIT_INVARIANT and envelope["reason_code"] == "LOCK_HOLDER_IS_LIVE"


def test_recover_lock_clears_a_lock_whose_holder_is_gone(campaign) -> None:
    build, store, _matrix = campaign
    instance = build()
    store.root.mkdir(parents=True, exist_ok=True)
    import socket

    store.lock_path.write_text(
        json.dumps({"pid": 2**30, "hostname": socket.gethostname(), "command": "watch"}),
        encoding="utf-8",
    )
    code, envelope = instance.recover_lock()
    assert code == EXIT_OK and envelope["decision"] == "LOCK_CLEARED"
    assert not store.lock_path.exists()


def test_recover_lock_will_not_guess_about_another_host(campaign) -> None:
    build, store, _matrix = campaign
    instance = build()
    store.root.mkdir(parents=True, exist_ok=True)
    store.lock_path.write_text(
        json.dumps({"pid": 1, "hostname": "some-other-host", "command": "watch"}), encoding="utf-8"
    )
    code, envelope = instance.recover_lock()
    assert code == EXIT_INVARIANT
    assert envelope["reason_code"] == "LOCK_HOLDER_ON_ANOTHER_HOST"



def test_plan_carries_the_durable_artifact_destination(campaign) -> None:
    """`storage.mode=s3` without a bucket fails inside the paid job, not here."""
    build, *_ = campaign
    _code, planned = build().plan("reacher", 0)
    command = planned["plan"]["command"]
    assert "--set" in command
    assert "storage.bucket=sim2policy-artifacts" in command
    assert "storage.endpoint_url=https://storage.eu-north1.nebius.cloud" in command
    assert "storage.region=eu-north1" in command


def test_every_example_enables_durable_storage_not_just_the_sb3_path(
    campaign, g1_campaign
) -> None:
    """G1 builds its own command, and an ArtifactStore is inert unless mode is s3.

    G1 trained for an hour twice and durably wrote nothing, because its branch
    passed bucket/endpoint/region but never the mode that turns writes on.
    """
    build, *_ = campaign
    g1_build, *_ = g1_campaign
    for example, seed, instance in (
        ("reacher", 0, build()),
        ("go1", 0, build()),
        ("g1", 0, g1_build()),
    ):
        _code, planned = instance.plan(example, seed)
        command = planned["plan"]["command"]
        assert "storage.mode=s3" in command, f"{example} would write nothing durably"
        assert "storage.bucket=sim2policy-artifacts" in command


def test_plan_carries_the_execution_location_the_job_cannot_derive(campaign) -> None:
    """A workload entry point refuses to start without this; the job cannot infer it."""
    build, *_ = campaign
    _code, planned = build().plan("reacher", 0)
    environment = planned["plan"]["environment"]
    assert environment["SIM2POLICY_EXECUTION_LOCATION"] == "nebius"
    assert environment["SIM2POLICY_COMMAND_CLASS"] == "training"
    assert environment["SIM2POLICY_NEBIUS_RESOURCE_ID"] == planned["plan"]["run_id"]
    assert environment["SIM2POLICY_IMMUTABLE_REVISION"] == "git:" + "a" * 40


def test_plan_carries_the_curation_evidence_the_job_cannot_invent(campaign) -> None:
    """Seed roles, ranking, acceptance, and the image digest are campaign-owned.

    A run whose published metrics omit them cannot pass verification, so they are
    declared in the reviewed plan rather than left to the job.
    """
    build, _store, matrix = campaign
    _code, planned = build().plan("reacher", 0)
    plan = planned["plan"]
    command = plan["command"]

    seed_roles = json.loads(command[command.index("--seed-roles-json") + 1])
    assert seed_roles["training"] == [0]
    assert seed_roles["selection"] == list(matrix.campaign["selection"]["seeds"])
    assert seed_roles["final"] == list(matrix.campaign["final"]["seeds"])
    assert not set(seed_roles["selection"]) & set(seed_roles["final"])

    ranking = json.loads(command[command.index("--ranking-explanation-json") + 1])
    assert ranking["kind"] == "mean_reward"
    acceptance = json.loads(command[command.index("--acceptance-criteria-json") + 1])
    assert acceptance["hard"]["mean_reward"] == -10
    assert acceptance["preferred"]["mean_reward"] == -7

    # One joined argument string reaches the container, so no argument may
    # contain whitespace that a naive split could break apart.
    assert not any(" " in argument for argument in command)

    assert plan["environment"]["SIM2POLICY_RUNTIME_IMAGE"] == plan["image_reference"]
    assert "@sha256:" in plan["environment"]["SIM2POLICY_RUNTIME_IMAGE"]


def test_plan_refuses_an_unconfigured_artifact_destination(campaign) -> None:
    build, store, matrix = campaign
    instance = Campaign(
        store,
        matrix,
        provider=FakeProvider(),
        prober=FakeProber(),
        environment={"SIM2POLICY_IMMUTABLE_REVISION": "git:" + "a" * 40},
    )
    with pytest.raises(CampaignError, match="durable artifact destination"):
        instance.build_plan("reacher", 0)

# -- preflight and location -------------------------------------------------


def test_preflight_blocks_while_a_job_is_active(campaign) -> None:
    build, *_ = campaign
    instance = build()
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    code, envelope = instance.preflight("reacher")
    assert code == EXIT_NEEDS_HUMAN and envelope["reason_code"] == "ACTIVE_JOB_PRESENT"


def test_preflight_passes_on_a_clean_campaign(campaign) -> None:
    build, *_ = campaign
    prober = FakeProber()
    code, envelope = build(prober=prober).preflight("reacher")
    assert code == EXIT_OK, envelope.get("failed_checks")
    assert envelope["checks"]["non_preemptible"] is True
    assert envelope["checks"]["nebius_quality_gates"] is True
    assert envelope["checks"]["cloud_baseline"] is True
    # The probes are given the reviewed revision and the exact card hardware.
    assert prober.calls[0]["expected_revision"] == "git:" + "a" * 40
    assert prober.calls[0]["hardware"]["platform"] == "cpu-d3"


def test_preflight_records_a_persistent_probe_audit(campaign) -> None:
    build, store, _matrix = campaign
    build().preflight("reacher")
    audit = store.read_json(store.audit_path("preflight.json"))
    assert audit is not None and audit["example"] == "reacher"
    assert [probe["name"] for probe in audit["probes"]] == [
        "repository", "infrastructure", "credentials", "preset_quota"
    ]


@pytest.mark.parametrize(
    ("failing", "reason"),
    [
        ("repository", "REVISION_MISMATCH"),
        ("infrastructure", "INFRASTRUCTURE_UNRESOLVED"),
        ("credentials", "CREDENTIALS_UNAVAILABLE"),
        ("preset_quota", "PRESET_OR_QUOTA_INSUFFICIENT"),
    ],
)
def test_preflight_blocks_on_each_failed_live_probe(campaign, failing: str, reason: str) -> None:
    build, *_ = campaign
    code, envelope = build(prober=FakeProber(failing={failing})).preflight("reacher")
    assert code == EXIT_NEEDS_HUMAN and envelope["reason_code"] == reason
    assert f"probe_{failing}" in envelope["failed_checks"]


def test_preflight_fails_closed_without_a_prober(campaign) -> None:
    """No cloud visibility must block a paid attempt, not silently pass it."""
    build, *_ = campaign
    instance = build()
    instance.prober = None
    code, envelope = instance.preflight("reacher")
    assert code == EXIT_NEEDS_HUMAN
    assert envelope["reason_code"] == "PREFLIGHT_PROBES_UNAVAILABLE"


def test_preflight_never_lets_a_github_result_decide(campaign) -> None:
    """A red informational run does not block, and a green one cannot substitute."""
    build, store, _matrix = campaign
    code, envelope = build().preflight("reacher")
    assert code == EXIT_OK
    assert envelope["informational"][0]["name"] == "github_actions"
    assert not any(name.startswith("probe_github") for name in envelope["checks"])

    # A GitHub-shaped preparation attestation cannot satisfy the Nebius gate.
    store.write_json(
        store.evidence_path("sb3-smoke.json"),
        {"provider": "github", "workflow": "smoke.yml", "conclusion": "success"},
    )
    code, envelope = build().preflight("reacher")
    assert code == EXIT_NEEDS_HUMAN
    assert "nebius_quality_gates" in envelope["failed_checks"]


def test_preflight_blocks_on_an_unaccounted_running_job(campaign) -> None:
    build, *_ = campaign
    provider = FakeProvider(audit_result={"active_jobs": ["aijob-someone-else"], "running_instances": []})
    code, envelope = build(provider=provider).preflight("reacher")
    assert code == EXIT_NEEDS_HUMAN and envelope["reason_code"] == "UNACCOUNTED_RESOURCE"
    assert envelope["unaccounted_resources"] == ["aijob-someone-else"]


def test_preflight_blocks_when_the_cloud_cannot_be_audited(campaign) -> None:
    build, *_ = campaign
    code, envelope = build(provider=BlockedProvider()).preflight("reacher")
    assert code == EXIT_NEEDS_HUMAN and envelope["reason_code"] == "UNACCOUNTED_RESOURCE"
    assert envelope["checks"]["cloud_baseline"] is False


def test_campaign_commands_refuse_to_run_outside_nebius() -> None:
    """The host is a control terminal; a workload entry point must not start here."""
    with pytest.raises(ExecutionLocationError, match="EXECUTION_LOCATION_INVALID"):
        require_nebius_execution("campaign", environment={"SIM2POLICY_EXECUTION_LOCATION": "local"})


def test_handoff_writes_the_documented_sections_without_secrets(campaign) -> None:
    build, store, _matrix = campaign
    instance = build()
    code, envelope = instance.handoff()
    assert code == EXIT_OK
    report = store.handoff_path.read_text(encoding="utf-8")
    for heading in ("## Campaign handoff", "- Campaign ID:", "- Matrix digest:", "- Cleanup audit result:"):
        assert heading in report
    assert "Safe operator note" in report
    assert envelope["handoff"]["campaign_id"] == "gallery-result-20260726"
