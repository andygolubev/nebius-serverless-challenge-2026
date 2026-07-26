"""Campaign state machine: idempotency, serialization, resume, and fail-closed stops."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sim2policy.campaign_provider import JobStatus, ProviderError
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
        "selected_checkpoint": {"effective_step": 800000, "sha256": "c" * 64},
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


@pytest.fixture()
def campaign(tmp_path: Path):
    """An initialized campaign whose implementation gate has passed."""
    matrix = load_matrix(MATRIX)
    store = CampaignStore(tmp_path, "gallery-result-20260726")

    def build(provider=None, evidence=None, **kwargs):
        instance = Campaign(
            store,
            matrix,
            provider=provider or FakeProvider(),
            evidence_reader_factory=evidence,
            sleeper=lambda _s: None,
            environment={
                "SIM2POLICY_IMMUTABLE_REVISION": "git:" + "a" * 40,
                "SIM2POLICY_BRANCH": "debug-portal",
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
            payload |= {"tag": f"registry.example/sim2policy-{name.split('-')[0]}", "digest": IMAGE_DIGEST}
        store.write_json(store.evidence_path(name), payload)
    instance.implementation_gate()
    return build, store, matrix


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


def _submitted_and_terminal(build, run_id: str, matrix, *, preferred: bool = True, documents=None):
    provider = FakeProvider(states=["COMPLETED"])
    evidence = FakeEvidence(documents or _run_documents(run_id, matrix.digest, preferred=preferred))
    instance = build(provider=provider, evidence=evidence)
    _code, planned = instance.plan("reacher", 0)
    instance.submit("reacher", 0, planned["plan"]["plan_digest"])
    instance.watch(poll_seconds=0, until_terminal=True)
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


def test_cleanup_passes_and_closes_the_attempt(campaign) -> None:
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix)
    instance.verify("reacher", 0)
    code, envelope = instance.cleanup()
    assert code == EXIT_OK and envelope["decision"] == "CLEANED"
    assert store.read()["attempts"]["reacher:0:base"]["state"] == "CLEANED"


def test_select_records_the_winner_and_skips_the_extension_when_quality_is_met(campaign) -> None:
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix)
    instance.verify("reacher", 0)
    code, envelope = instance.select("reacher")
    assert code == EXIT_OK
    assert envelope["decision"] == "EXTENSION_SKIPPED_QUALITY_MET"
    assert envelope["selection"]["checkpoint_sha256"] == "c" * 64
    assert envelope["next_command"] == "accept --example reacher"


def test_select_requires_an_extension_when_the_preferred_target_is_missed(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix, preferred=False)
    instance.verify("reacher", 0)
    code, envelope = instance.select("reacher")
    assert code == EXIT_OK and envelope["decision"] == "EXTENSION_REQUIRED"
    assert "--phase extension" in envelope["next_command"]


def test_accept_needs_a_human_when_only_the_hard_floor_passes(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix, preferred=False)
    instance.verify("reacher", 0)
    instance.cleanup()
    instance.select("reacher")
    code, envelope = instance.accept("reacher")
    assert code == EXIT_NEEDS_HUMAN
    assert envelope["reason_code"] == "NEEDS_HUMAN_QUALITY_TARGET"


def test_accept_is_pin_ready_only_with_hard_preferred_and_cleanup(campaign) -> None:
    build, _store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix)
    instance.verify("reacher", 0)

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
    build, store, matrix = campaign
    run_id = "showcase-gallery-result-20260726-reacher-s0"
    instance = _submitted_and_terminal(build, run_id, matrix, preferred=False)
    instance.verify("reacher", 0)
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
    code, envelope = build().preflight("reacher")
    assert code == EXIT_OK, envelope.get("failed_checks")
    assert envelope["checks"]["non_preemptible"] is True


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
