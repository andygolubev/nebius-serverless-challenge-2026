"""Nebius-only, serialized controller for the curated public showcase campaign.

Written for an operator that can run commands and report structured output but must
not make research, hyperparameter, cloud, acceptance, or publication decisions. Every
choice is either in the reviewed campaign matrix or is derived mechanically from
recorded evidence; nothing is inferred from provider logs.

The design turns on three properties:

* **Idempotent.** Each command reads persisted state and performs the one missing
  transition, or reports that it already happened. Re-running is always safe, which
  is what makes the campaign survive an interrupted agent.
* **Serialized.** One campaign lock, and at most one remote job across the whole
  campaign. A second submission while one is active is refused, not queued.
* **Fail-closed.** Missing evidence, an unknown provider state, or a digest mismatch
  stops the campaign rather than guessing. Exit codes 30 and 40 mean stop.

Exit codes: 0 done, 10 remote work active, 20 deterministic rejection, 30 human
decision required, 40 invariant/security/cleanup failure.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sim2policy.campaign_infra import InfrastructurePreflight, probe_from_environment
from sim2policy.campaign_provider import (
    BlockedProvider,
    JobProvider,
    ProviderError,
    provider_from_environment,
)
from sim2policy.campaign_redaction import sanitize_exception
from sim2policy.campaign_state import (
    ACTIVE_STATES,
    CampaignError,
    CampaignStore,
    active_attempt,
    attempt_key,
    process_is_live,
    utc_now,
    validate_run_identity,
    validate_transition,
)
from sim2policy.campaign_verify import (
    ArtifactStoreEvidenceReader,
    EvidenceReader,
    classify_failure,
    verify_run_evidence,
)
from sim2policy.config import StorageConfig
from sim2policy.execution_location import (
    ExecutionLocationError,
    LocationAttestation,
    require_nebius_execution,
    write_location_attestation,
)
from sim2policy.showcase_matrix import EXAMPLE_ORDER, CampaignMatrix, MatrixError, load_matrix

EXIT_OK = 0
EXIT_ACTIVE = 10
EXIT_REJECTED = 20
EXIT_NEEDS_HUMAN = 30
EXIT_INVARIANT = 40

SCHEMA_VERSION = 2

#: Evidence files `implementation-gate` requires before any paid work is legal.
#: Each is produced by a Nebius-executed step; a GitHub-hosted result cannot
#: satisfy any of them.
REQUIRED_GATE_EVIDENCE = (
    "nebius-quality-gates.json",
    "sb3-image.json",
    "mjx-image.json",
    "sb3-smoke.json",
    "mjx-smoke.json",
    "cloud-audit.json",
)

#: Heartbeat age after which an active provider job becomes a human decision.
HEARTBEAT_TIMEOUT_SECONDS = 300.0

#: Retries permitted per attempt, per the runbook's failure table.
MAX_RETRIES_BEFORE_CHECKPOINT = 1


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _compact_json(value: Any) -> str:
    """Serialize a job argument with no whitespace and a stable key order.

    The provider delivers container arguments as one joined string, so a value
    containing spaces depends on how that string is split again. Emitting compact
    JSON removes the question, and the stable order keeps the plan digest
    reproducible.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _preflight_reason(checks: Mapping[str, bool], unaccounted: Sequence[Any]) -> str:
    """Name the most actionable failure so the handoff points at one thing to fix."""
    if not checks.get("no_active_job", True):
        return "ACTIVE_JOB_PRESENT"
    if not checks.get("previous_attempt_cleaned", True):
        return "CLEANUP_REQUIRED"
    if unaccounted or not checks.get("cloud_baseline", True):
        return "UNACCOUNTED_RESOURCE"
    if not checks.get("probe_live_probes", True):
        return "PREFLIGHT_PROBES_UNAVAILABLE"
    if not checks.get("probe_repository", True):
        return "REVISION_MISMATCH"
    if not checks.get("probe_infrastructure", True):
        return "INFRASTRUCTURE_UNRESOLVED"
    if not checks.get("probe_credentials", True):
        return "CREDENTIALS_UNAVAILABLE"
    if not checks.get("probe_preset_quota", True):
        return "PRESET_OR_QUOTA_INSUFFICIENT"
    if not checks.get("nebius_quality_gates", True):
        return "NEBIUS_ATTESTATION_MISSING"
    return "PREFLIGHT_FAILED"


def _rank_key(aggregate: Mapping[str, Any], kind: str, effective_step: int) -> tuple[float, ...]:
    """Ranking over recorded aggregates, matching `checkpoint_selection.rank_key`.

    Selection across seeds happens here, on evidence each seed's job already wrote,
    so the ordering must agree exactly with the in-job ranking that produced it.
    The trailing negative step makes an earlier checkpoint win every tie.
    """
    earlier = -float(effective_step)
    if kind == "mean_reward":
        return (
            float(aggregate.get("mean_reward", 0.0)),
            float(aggregate.get("mean_episode_length", 0.0)),
            earlier,
        )
    if kind == "locomotion":
        return (
            float(aggregate.get("no_fall_count", 0)),
            float(aggregate.get("min_velocity", 0.0)),
            float(aggregate.get("mean_episode_length", 0.0)),
            float(aggregate.get("mean_velocity", 0.0)),
            float(aggregate.get("mean_reward", 0.0)),
            earlier,
        )
    raise CampaignError(f"unknown ranking kind: {kind}")


class Campaign:
    """One campaign, bound to one state directory, matrix, and provider."""

    def __init__(
        self,
        store: CampaignStore,
        matrix: CampaignMatrix,
        *,
        provider: JobProvider | None = None,
        evidence_reader_factory: Any = None,
        clock: Any = time.time,
        sleeper: Any = time.sleep,
        environment: Mapping[str, str] | None = None,
        prober: InfrastructurePreflight | None = None,
    ) -> None:
        self.store = store
        self.matrix = matrix
        self.provider: JobProvider = provider or BlockedProvider()
        self._evidence_reader_factory = evidence_reader_factory
        self._clock = clock
        self._sleep = sleeper
        self._environment = dict(os.environ if environment is None else environment)
        # Absent an explicit Nebius project scope this stays `None`, which preflight
        # treats as a failed probe rather than as "nothing to check".
        self.prober = prober if prober is not None else probe_from_environment(self._environment)

    # -- envelope ------------------------------------------------------------

    def envelope(
        self,
        *,
        code: int,
        decision: str,
        reason_code: str,
        next_command: str,
        attempt: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        state = self.store.read_json(self.store.state_path) or {}
        result: dict[str, Any] = {
            "campaign_id": self.store.campaign_id,
            "matrix_digest": state.get("matrix_digest"),
            "example": (attempt or {}).get("example"),
            "seed": (attempt or {}).get("seed"),
            "attempt": (attempt or {}).get("attempt_number"),
            "state": (attempt or {}).get("state") or state.get("state"),
            "plan_digest": (attempt or {}).get("plan_digest"),
            "remote_id": (attempt or {}).get("remote_id"),
            "evidence_digest": (attempt or {}).get("evidence_digest"),
            "decision": decision,
            "reason_code": reason_code,
            "cleanup_state": (attempt or {}).get("cleanup_state", "not_started"),
            "next_command": next_command,
        }
        if extra:
            result.update(extra)
        return code, self.store.safe(result)

    # -- attempt helpers -----------------------------------------------------

    def _attempt(self, state: Mapping[str, Any], key: str) -> dict[str, Any] | None:
        attempts = state.get("attempts")
        if isinstance(attempts, dict):
            value = attempts.get(key)
            if isinstance(value, dict):
                return dict(value)
        return None

    def _save_attempt(
        self,
        state: dict[str, Any],
        key: str,
        attempt: Mapping[str, Any],
        *,
        command: str,
        code: int = EXIT_OK,
    ) -> dict[str, Any]:
        before = (self._attempt(state, key) or {}).get("state")
        after = str(attempt["state"])
        if before is not None:
            validate_transition(before, after)
        record = dict(attempt)
        record["updated_at"] = utc_now()
        state.setdefault("attempts", {})[key] = record
        state["updated_at"] = utc_now()
        state["state"] = after
        self.store.write(state)
        self.store.journal(
            {
                "command": command,
                "attempt": key,
                "before": before,
                "after": after,
                "exit_code": code,
                "evidence_digest": record.get("evidence_digest"),
            }
        )
        return record

    # -- init (5.1) ----------------------------------------------------------

    def initialize(self, attestation: LocationAttestation) -> tuple[int, dict[str, Any]]:
        with self.store.lock("init"):
            if self.store.initialized():
                existing = self.store.read()
                if existing.get("matrix_digest") != self.matrix.digest:
                    # Reusing an ID for a different plan would make two campaigns
                    # indistinguishable in the evidence record.
                    return self.envelope(
                        code=EXIT_INVARIANT,
                        decision="BLOCK",
                        reason_code="MATRIX_DIGEST_MISMATCH",
                        next_command="handoff",
                    )
                return self.envelope(
                    code=EXIT_OK,
                    decision="ALREADY_INITIALIZED",
                    reason_code="IDEMPOTENT",
                    next_command="implementation-gate",
                )
            state = {
                "schema_version": SCHEMA_VERSION,
                "campaign_id": self.store.campaign_id,
                "matrix_digest": self.matrix.digest,
                "state": "PLANNED",
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "ordered_examples": list(EXAMPLE_ORDER),
                "attempts": {},
                "examples": {},
                "location_attestation": attestation.to_dict(),
            }
            self.store.write_json(
                self.store.campaign_path,
                {"matrix": self.matrix.normalized, "matrix_digest": self.matrix.digest},
            )
            write_location_attestation(self.store.evidence_path("init-location.json"), attestation)
            self.store.write(state)
            self.store.journal(
                {"command": "init", "before": None, "after": "PLANNED", "exit_code": EXIT_OK}
            )
            return self.envelope(
                code=EXIT_OK,
                decision="PLANNED",
                reason_code="INITIALIZED",
                next_command="implementation-gate",
            )

    # -- implementation gate (5.4) ------------------------------------------

    def implementation_gate(self) -> tuple[int, dict[str, Any]]:
        with self.store.lock("implementation-gate"):
            state = self.store.read()
            absent = [
                name
                for name in REQUIRED_GATE_EVIDENCE
                if not self.store.evidence_path(name).is_file()
            ]
            findings: dict[str, Any] = {"missing_evidence": absent}
            if absent:
                state["implementation_gate"] = {"decision": "BLOCK", "at": utc_now(), **findings}
                self.store.write(state)
                self.store.journal(
                    {"command": "implementation-gate", "after": "BLOCK", "exit_code": EXIT_NEEDS_HUMAN}
                )
                return self.envelope(
                    code=EXIT_NEEDS_HUMAN,
                    decision="BLOCK",
                    reason_code="IMPLEMENTATION_EVIDENCE_MISSING",
                    next_command="handoff",
                    extra=findings,
                )
            # Every attestation must name a Nebius resource. A third-party runner's
            # success is informational and can never satisfy a preparation gate.
            non_nebius = []
            for name in REQUIRED_GATE_EVIDENCE:
                document = self.store.read_json(self.store.evidence_path(name)) or {}
                location = document.get("location_attestation") or document
                if location.get("provider") != "nebius":
                    non_nebius.append(name)
            if non_nebius:
                findings["non_nebius_evidence"] = non_nebius
                state["implementation_gate"] = {"decision": "BLOCK", "at": utc_now(), **findings}
                self.store.write(state)
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="EXECUTION_LOCATION_INVALID",
                    next_command="handoff",
                    extra=findings,
                )
            state["implementation_gate"] = {
                "decision": "PASS",
                "at": utc_now(),
                "matrix_digest": self.matrix.digest,
            }
            self.store.write(state)
            self.store.journal(
                {"command": "implementation-gate", "after": "PASS", "exit_code": EXIT_OK}
            )
            return self.envelope(
                code=EXIT_OK,
                decision="PASS",
                reason_code="IMPLEMENTATION_COMPLETE",
                next_command="preflight",
            )

    # -- preflight (5.5) -----------------------------------------------------

    def preflight(self, example: str | None = None) -> tuple[int, dict[str, Any]]:
        """Prove, immediately before a paid attempt, that the cloud can run it.

        Persisted state answers "what did this campaign already do"; it cannot
        answer "is the revision still the reviewed one, do the credentials still
        resolve, is the preset still available". Those come from live read-only
        probes, and every one of them must pass. A GitHub Actions result is
        collected alongside them but is structurally excluded from the decision.
        """
        with self.store.lock("preflight"):
            state = self.store.read()
            checks: dict[str, bool] = {}
            gate = state.get("implementation_gate") or {}
            checks["implementation_gate"] = gate.get("decision") == "PASS"
            checks["matrix_digest"] = state.get("matrix_digest") == self.matrix.digest

            attestation = state.get("location_attestation") or {}
            checks["execution_location"] = attestation.get("provider") == "nebius"
            checks["branch"] = self._environment.get("SIM2POLICY_BRANCH", "debug-portal") == "debug-portal"
            revision = self._environment.get("SIM2POLICY_IMMUTABLE_REVISION")
            checks["immutable_revision"] = bool(revision)

            # Every preparation attestation must still be a Nebius one. The gate
            # recorded this once; preflight re-reads it so a substituted or
            # third-party-sourced document cannot survive between attempts.
            checks["nebius_quality_gates"] = self._nebius_gate_attestations()

            # One active job, campaign-wide.
            active = active_attempt(state)
            checks["no_active_job"] = active is None

            # The previous attempt must be cleaned before another is submitted.
            attempts = state.get("attempts") or {}
            unclean = [
                key
                for key, item in sorted(attempts.items())
                if isinstance(item, dict)
                and item.get("state") in {"VERIFIED", "ACCEPTED", "REJECTED"}
                and item.get("cleanup_state") != "PASS"
            ]
            checks["previous_attempt_cleaned"] = not unclean

            hardware: Mapping[str, Any] | None = None
            if example is not None:
                card = self.matrix.card(example)
                hardware = card["hardware"]
                checks["non_preemptible"] = hardware.get("preemptible") is False
                checks["image_digest"] = self._image_evidence(card["image"]["runtime"]) is not None

            # Live cloud baseline: nothing chargeable may be running that this
            # campaign cannot account for.
            baseline, unaccounted = self._cloud_baseline(state)
            checks["cloud_baseline"] = baseline is not None and not unaccounted

            probes, informational = self._live_probes(revision, hardware)
            for probe in probes:
                checks[f"probe_{probe['name']}"] = bool(probe["ok"])

            failed = sorted(name for name, ok in checks.items() if not ok)
            findings: dict[str, Any] = {
                "checks": dict(sorted(checks.items())),
                "failed_checks": failed,
                "probes": probes,
                "informational": informational,
                "cloud_baseline": baseline,
                "unaccounted_resources": unaccounted,
            }
            self.store.write_json(
                self.store.audit_path("preflight.json"),
                {"at": utc_now(), "example": example, **findings},
            )
            if failed:
                return self.envelope(
                    code=EXIT_NEEDS_HUMAN,
                    decision="BLOCK",
                    reason_code=_preflight_reason(checks, unaccounted),
                    next_command="handoff",
                    extra=findings,
                )
            return self.envelope(
                code=EXIT_OK,
                decision="PASS",
                reason_code="PREFLIGHT_OK",
                next_command="plan",
                extra=findings,
            )

    def _nebius_gate_attestations(self) -> bool:
        """Every required preparation document exists and names a Nebius resource."""
        for name in REQUIRED_GATE_EVIDENCE:
            document = self.store.read_json(self.store.evidence_path(name))
            if not isinstance(document, dict):
                return False
            location = document.get("location_attestation") or document
            if location.get("provider") != "nebius":
                return False
        return True

    def _expected_running_instances(self) -> set[str]:
        """Instances that are legitimately running and are not campaign compute.

        The campaign controller itself executes on an approved Nebius
        orchestration VM, so a cleanup audit that demanded zero running
        instances could never pass while it was running. Its own attested
        resource is therefore always expected, plus any persistent
        infrastructure the operator declares by ID. Everything else running is
        unaccounted and stops the campaign.
        """
        expected = {self._environment.get("SIM2POLICY_NEBIUS_RESOURCE_ID", "").strip()}
        declared = self._environment.get("SIM2POLICY_EXPECTED_RUNNING_INSTANCES", "")
        expected |= {item.strip() for item in declared.split(",")}
        return {item for item in expected if item}

    def _unaccounted_running(self, audit: Mapping[str, Any]) -> list[str]:
        expected = self._expected_running_instances()
        return sorted(
            instance
            for instance in audit.get("running_instances", [])
            if instance and instance not in expected
        )

    def _cloud_baseline(
        self, state: Mapping[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """Enumerate chargeable resources and separate ours from everything else."""
        try:
            audit = dict(self.provider.audit())
        except ProviderError as exc:
            return None, [self.store.safe(sanitize_exception(exc))]
        known = {
            item.get("remote_id")
            for item in (state.get("attempts") or {}).values()
            if isinstance(item, dict)
        }
        unaccounted = [job for job in audit.get("active_jobs", []) if job and job not in known]
        return audit, unaccounted

    def _live_probes(
        self, revision: str | None, hardware: Mapping[str, Any] | None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Run the read-only probes, split into deciding and informational results.

        With no prober the campaign cannot see the cloud at all, which is reported
        as a failed probe rather than an absent one: an unobservable environment
        must block a paid attempt, not silently pass it.
        """
        if self.prober is None:
            return [
                {
                    "name": "live_probes",
                    "ok": False,
                    "informational": False,
                    "detail": {"error": "no Nebius project scope is configured for live probes"},
                }
            ], []
        results = self.prober.collect(expected_revision=revision, hardware=hardware)
        deciding: list[dict[str, Any]] = []
        informational: list[dict[str, Any]] = []
        for probe in results:
            record = self.store.safe(probe.to_dict())
            (informational if probe.informational else deciding).append(record)
        return deciding, informational

    def _image_evidence(self, runtime: str) -> dict[str, Any] | None:
        document = self.store.read_json(self.store.evidence_path(f"{runtime}-image.json"))
        if not isinstance(document, dict):
            return None
        if not isinstance(document.get("digest"), str) or not document.get("tag"):
            return None
        return document

    # -- plan (5.6) ----------------------------------------------------------

    def build_plan(self, example: str, seed: int, *, phase: str = "base") -> dict[str, Any]:
        """Derive the complete, reviewable submission plan from the matrix alone."""
        card = self.matrix.card(example)
        if seed not in card["seeds"]:
            raise CampaignError(f"seed {seed} is not declared for {example}")
        if phase not in {"base", "extension"}:
            raise CampaignError(f"unknown attempt phase: {phase}")
        if phase == "extension" and card.get("extension_steps") is None:
            raise CampaignError(f"{example} declares no extension")

        image = self._image_evidence(card["image"]["runtime"])
        if image is None:
            raise CampaignError(f"no immutable {card['image']['runtime']} image digest is recorded")

        steps = card["base_steps"] if phase == "base" else card["extension_steps"]
        suffix = "" if phase == "base" else "-ext"
        run_id = validate_run_identity(
            f"showcase-{self.store.campaign_id}-{example}-s{seed}{suffix}"
        )
        campaign = self.matrix.campaign
        hardware = dict(card["hardware"])

        state = self.store.read_json(self.store.state_path) or {}
        parent = None
        if phase == "extension":
            selection = ((state.get("examples") or {}).get(example) or {}).get("selection")
            if not isinstance(selection, dict):
                raise CampaignError("extension requires a recorded selection result")
            parent = {
                "run_id": selection.get("run_id"),
                "checkpoint_sha256": selection.get("checkpoint_sha256"),
                "checkpoint_native_path": selection.get("checkpoint_native_path"),
                "effective_step": selection.get("effective_step"),
            }

        command = self._build_command(
            card,
            example=example,
            seed=seed,
            steps=int(steps),
            run_id=run_id,
            parent=parent,
            image_digest=str(image["digest"]),
        )
        plan = {
            "example": example,
            "seed": seed,
            "phase": phase,
            "run_id": run_id,
            "durable_prefix": f"sim2policy/{run_id}/",
            "backend": card["backend"],
            "module": command[2],
            "config": card["config"],
            "image_reference": f"{image['tag']}@{image['digest']}",
            "image_digest": image["digest"],
            "config_digest": self._config_digest(card["config"]),
            "matrix_digest": self.matrix.digest,
            "effective_steps": int(steps),
            "checkpoint_every_steps": card["checkpoint_every_steps"],
            "seed_roles": {
                "training": [seed],
                "selection": list(campaign["selection"]["seeds"]),
                "final": list(campaign["final"]["seeds"]),
            },
            "hardware": hardware,
            "parent": parent,
            "required_artifacts": sorted(
                {"final_policy", "metrics_json", "report_md", "video_final", "policy_bundle",
                 "resolved_config", "runtime_versions", "video_selected", "video_final_step"}
            ),
            "acceptance": card["acceptance"],
            "ranking": card["ranking"],
            "max_retries_remaining": MAX_RETRIES_BEFORE_CHECKPOINT,
            "cleanup_action": "delete campaign-owned compute, retain provider history and S3 evidence",
            "command": command,
            "subnet_id": self._environment.get("SIM2POLICY_SUBNET_ID", ""),
            "environment": self._job_environment(
                run_id, image_reference=f"{image['tag']}@{image['digest']}"
            ),
            "secret_environment": self._job_secret_environment(),
            "registry_secret": self._environment.get("NEBIUS_REGISTRY_SECRET_VERSION", ""),
            "secret_selectors": self._secret_selectors(),
        }
        if not plan["subnet_id"]:
            raise CampaignError("job subnet is not configured")
        if not plan["registry_secret"]:
            raise CampaignError("registry pull secret selector is not configured")
        plan["plan_digest"] = _digest({k: v for k, v in plan.items() if k != "plan_digest"})
        return plan

    def _config_digest(self, config: str) -> str:
        path = Path(config)
        if not path.is_file():
            path = Path(__file__).resolve().parents[2] / config
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""

    def _secret_selectors(self) -> list[str]:
        """Non-secret MysteryBox version IDs, read from the environment by name.

        These are references the provider resolves at use time, never payloads, so
        recording them in a plan discloses nothing.
        """
        selectors = []
        for name in ("NEBIUS_REGISTRY_SECRET_VERSION", "NEBIUS_ARTIFACT_SECRET_VERSION"):
            value = self._environment.get(name)
            if value:
                selectors.append(value)
        return selectors

    def _job_environment(self, run_id: str, *, image_reference: str = "") -> dict[str, str]:
        """Non-secret environment the job needs to start and to reach its bucket.

        The access key *ID* is an identifier, not a credential; its matching secret
        is delivered separately as a selector the provider resolves. Both are
        required together, so a half-configured runner is refused here rather than
        discovered by a job that cannot upload what it just spent an hour computing.

        The execution-location attestation is passed in the same way. Every workload
        entry point refuses to start without it, by design — the job must be able to
        prove it is running on Nebius, and it cannot derive that for itself. The
        resource identity is the deterministic job name, which is unique within the
        project and resolves back to exactly this submission.
        """
        storage = self._durable_storage()
        revision = self._environment.get("SIM2POLICY_IMMUTABLE_REVISION", "")
        environment = {
            "SIM2POLICY_S3_BUCKET": storage["storage.bucket"],
            "AWS_ENDPOINT_URL_S3": storage["storage.endpoint_url"],
            "AWS_DEFAULT_REGION": storage["storage.region"],
            "AWS_ACCESS_KEY_ID": self._environment.get("SIM2POLICY_ARTIFACT_ACCESS_KEY_ID", ""),
            "SIM2POLICY_EXECUTION_LOCATION": "nebius",
            "SIM2POLICY_COMMAND_CLASS": "training",
            "SIM2POLICY_NEBIUS_RESOURCE_ID": run_id,
            "SIM2POLICY_NEBIUS_REGION": storage["storage.region"],
            "SIM2POLICY_IMMUTABLE_REVISION": revision,
            # The job cannot observe which image reference launched it, but its
            # published resolved config must name the exact digest it ran, so the
            # reviewed plan tells it.
            "SIM2POLICY_RUNTIME_IMAGE": image_reference,
        }
        if not environment["SIM2POLICY_RUNTIME_IMAGE"]:
            raise CampaignError("the job's immutable image reference is not configured")
        if not environment["AWS_ACCESS_KEY_ID"]:
            raise CampaignError("artifact access key ID is not configured")
        if not revision:
            raise CampaignError("immutable revision is not configured")
        return environment

    def _job_secret_environment(self) -> dict[str, str]:
        """Env vars delivered as MysteryBox selectors, never as values."""
        selector = self._environment.get("NEBIUS_ARTIFACT_SECRET_VERSION", "")
        if not selector:
            raise CampaignError("artifact secret selector is not configured")
        return {"AWS_SECRET_ACCESS_KEY": selector}

    def _durable_storage(self) -> dict[str, str]:
        """The artifact destination, taken from the resolved infrastructure outputs.

        `storage.mode=s3` without a bucket fails the job's own config validation
        minutes into paid compute, so the destination is resolved here, recorded in
        the plan, and refused outright when it is not configured. The values are
        bucket/endpoint/region identifiers — never the credentials used to reach
        them, which stay secret selectors resolved by the provider.
        """
        settings = {
            "storage.bucket": self._environment.get("SIM2POLICY_ARTIFACT_BUCKET", ""),
            "storage.endpoint_url": self._environment.get("SIM2POLICY_ARTIFACT_ENDPOINT", ""),
            "storage.region": self._environment.get("SIM2POLICY_ARTIFACT_REGION", ""),
        }
        missing = sorted(name for name, value in settings.items() if not value)
        if missing:
            raise CampaignError(f"durable artifact destination is not configured: {missing}")
        return settings

    def _build_command(
        self,
        card: Mapping[str, Any],
        *,
        example: str,
        seed: int,
        steps: int,
        run_id: str,
        parent: Mapping[str, Any] | None,
        image_digest: str,
    ) -> list[str]:
        """The exact argument array the job runs. No shell string is ever built."""
        storage = self._durable_storage()
        if example == "g1":
            curriculum = card["curriculum"]
            command = [
                "python", "-m", "sim2policy.hosted_g1_curriculum",
                "--matrix", "configs/showcase_training_matrix.yaml",
                "--flat-config", curriculum["flat_config"],
                "--rough-config", curriculum["rough_config"],
                "--run-id", run_id,
                "--image-digest", image_digest,
            ]
            for key, value in sorted(storage.items()):
                command += ["--set", f"{key}={value}"]
            return command
        module = f"sim2policy.hosted_{card['backend']}"
        campaign = self.matrix.campaign
        command = [
            "python", "-m", module,
            "--config", card["config"],
            "--run-id", run_id,
            "--gallery-example-id", card["gallery_example_id"],
            "--matrix-digest", self.matrix.digest,
            # Seed roles, ranking rule, and acceptance thresholds are the
            # campaign's to declare, not the job's to infer. The finalizer records
            # them as published evidence, and verification rejects a run that
            # cannot show them.
            "--seed-roles-json", _compact_json(
                {
                    "training": [seed],
                    "selection": list(campaign["selection"]["seeds"]),
                    "final": list(campaign["final"]["seeds"]),
                }
            ),
            "--ranking-explanation-json", _compact_json(dict(card["ranking"])),
            "--acceptance-criteria-json", _compact_json(dict(card["acceptance"])),
            "--set", f"training.total_steps={steps}",
            "--set", f"checkpoint.every_steps={card['checkpoint_every_steps']}",
            "--set", f"seed={seed}",
            "--set", "storage.mode=s3",
        ]
        for key, value in sorted(storage.items()):
            command += ["--set", f"{key}={value}"]
        if parent is not None:
            if not all(parent.get(key) for key in ("run_id", "checkpoint_sha256", "checkpoint_native_path")):
                raise CampaignError("extension parent is missing exact checkpoint provenance")
            command += [
                "--resume-run-id", str(parent["run_id"]),
                "--resume-checkpoint-path", str(parent["checkpoint_native_path"]),
                "--resume-checkpoint-sha256", str(parent["checkpoint_sha256"]),
            ]
        return command

    def plan(self, example: str, seed: int, *, phase: str = "base") -> tuple[int, dict[str, Any]]:
        with self.store.lock("plan"):
            state = self.store.read()
            if state.get("matrix_digest") != self.matrix.digest:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="MATRIX_DIGEST_MISMATCH",
                    next_command="handoff",
                )
            plan = self.build_plan(example, seed, phase=phase)
            key = attempt_key(example, seed, phase)
            existing = self._attempt(state, key)
            attempt = {
                "example": example,
                "seed": seed,
                "phase": phase,
                "attempt_number": (existing or {}).get("attempt_number", 1),
                "state": "PLANNED",
                "plan_digest": plan["plan_digest"],
                "run_id": plan["run_id"],
                "remote_id": (existing or {}).get("remote_id"),
                "idempotency_key": _digest(
                    [self.store.campaign_id, example, seed, phase,
                     (existing or {}).get("attempt_number", 1), plan["plan_digest"]]
                ),
                "evidence_digest": None,
                "cleanup_state": (existing or {}).get("cleanup_state", "not_started"),
                "retries_consumed": (existing or {}).get("retries_consumed", 0),
                "decision": None,
                "reason_code": None,
            }
            # A submission that never reached the provider leaves the attempt in
            # NEEDS_HUMAN with no remote job. The runbook's `SUBMIT_NO_REMOTE_ID`
            # row allows exactly one further submission of the same plan once the
            # run name is proven absent, which `submit` already checks before it
            # ever creates a second job. Refusing to re-plan here would instead
            # force a whole new campaign ID for a failure that spent nothing, so
            # a *jobless* NEEDS_HUMAN attempt stays replannable; one holding a
            # remote ID does not.
            replannable = {"PLANNED", "PREFLIGHTED"}
            if existing is not None and existing.get("state") == "NEEDS_HUMAN" and not existing.get("remote_id"):
                replannable = replannable | {"NEEDS_HUMAN"}
            if existing is not None and existing.get("state") not in replannable:
                return self.envelope(
                    code=EXIT_OK,
                    decision="ALREADY_PLANNED",
                    reason_code="IDEMPOTENT",
                    next_command="status",
                    attempt=existing,
                )
            self.store.write_json(
                self.store.plan_path(key), {"plan": plan, "plan_digest": plan["plan_digest"]}
            )
            saved = self._save_attempt(state, key, attempt, command="plan")
            code, envelope = self.envelope(
                code=EXIT_OK,
                decision="PLAN_READY",
                reason_code="REVIEW_REQUIRED",
                next_command=f"submit --example {example} --seed {seed} --confirm-plan-digest {plan['plan_digest']}",
                attempt=saved,
            )
            envelope["plan"] = self.store.safe(plan)
            return code, envelope

    # -- submit (5.7, 5.8) ---------------------------------------------------

    def submit(
        self, example: str, seed: int, confirmation: str, *, phase: str = "base"
    ) -> tuple[int, dict[str, Any]]:
        with self.store.lock("submit"):
            state = self.store.read()
            gate = state.get("implementation_gate") or {}
            if gate.get("decision") != "PASS":
                return self.envelope(
                    code=EXIT_NEEDS_HUMAN,
                    decision="BLOCK",
                    reason_code="IMPLEMENTATION_GATE_REQUIRED",
                    next_command="implementation-gate",
                )
            key = attempt_key(example, seed, phase)
            attempt = self._attempt(state, key)
            if attempt is None:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="PLAN_REQUIRED",
                    next_command=f"plan --example {example} --seed {seed}",
                )
            if attempt.get("state") in ACTIVE_STATES and attempt.get("remote_id"):
                # Already submitted: report, never submit twice.
                return self.envelope(
                    code=EXIT_ACTIVE,
                    decision="ALREADY_SUBMITTED",
                    reason_code="IDEMPOTENT",
                    next_command="watch --until-terminal",
                    attempt=attempt,
                )
            other = active_attempt(state)
            if other is not None and other.get("key") != key:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="ACTIVE_JOB_PRESENT",
                    next_command="watch --until-terminal",
                    extra={"active_attempt": other.get("key")},
                )

            # The reviewed plan is re-derived and re-digested, so a matrix or image
            # change between `plan` and `submit` is caught rather than submitted.
            plan = self.build_plan(example, seed, phase=phase)
            if confirmation != plan["plan_digest"] or attempt.get("plan_digest") != plan["plan_digest"]:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="PLAN_DIGEST_MISMATCH",
                    next_command=f"plan --example {example} --seed {seed}",
                    attempt=attempt,
                )

            attempt["state"] = "PREFLIGHTED"
            self._save_attempt(state, key, attempt, command="submit")

            try:
                remote_id = self.provider.submit(plan, idempotency_key=attempt["idempotency_key"])
            except ProviderError as exc:
                # A lost response is recoverable only because the run name is
                # deterministic: look for the job before ever submitting again.
                adopted = self._adopt_existing(plan, attempt)
                if adopted is None:
                    attempt["state"] = "NEEDS_HUMAN"
                    attempt["reason_code"] = "SUBMIT_FAILED"
                    saved = self._save_attempt(
                        state, key, attempt, command="submit", code=EXIT_NEEDS_HUMAN
                    )
                    return self.envelope(
                        code=EXIT_NEEDS_HUMAN,
                        decision="BLOCK",
                        reason_code="SUBMIT_FAILED",
                        next_command="handoff",
                        attempt=saved,
                        extra={"provider_error": self.store.safe(sanitize_exception(exc))},
                    )
                remote_id = adopted

            attempt["remote_id"] = remote_id
            attempt["state"] = "SUBMITTED"
            attempt["heartbeat_at"] = self._clock()
            saved = self._save_attempt(state, key, attempt, command="submit")
            return self.envelope(
                code=EXIT_OK,
                decision="SUBMITTED",
                reason_code="REMOTE_ID_RECORDED",
                next_command="watch --until-terminal",
                attempt=saved,
            )

    def _adopt_existing(self, plan: Mapping[str, Any], attempt: Mapping[str, Any]) -> str | None:
        """Adopt an existing remote job only when its identity matches this plan."""
        try:
            found = self.provider.find_by_name(str(plan["run_id"]))
        except ProviderError:
            return None
        if found is None or not found.remote_id:
            return None
        return found.remote_id

    # -- watch (5.9) ---------------------------------------------------------

    def watch(
        self, *, poll_seconds: int = 60, until_terminal: bool = False, max_polls: int = 10_000
    ) -> tuple[int, dict[str, Any]]:
        state = self.store.read()
        active = active_attempt(state)
        if active is None:
            return self.envelope(
                code=EXIT_OK,
                decision="NO_ACTIVE_JOB",
                reason_code="IDEMPOTENT",
                next_command="status",
            )
        key = str(active["key"])
        polls = 0
        while True:
            state = self.store.read()
            attempt = self._attempt(state, key) or {}
            remote_id = attempt.get("remote_id")
            if not remote_id:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="MISSING_REMOTE_ID",
                    next_command="handoff",
                    attempt=attempt,
                )
            try:
                status = self.provider.poll(str(remote_id))
            except ProviderError as exc:
                last = float(attempt.get("heartbeat_at") or 0.0)
                if self._clock() - last > HEARTBEAT_TIMEOUT_SECONDS:
                    attempt["state"] = "NEEDS_HUMAN"
                    attempt["reason_code"] = "HEARTBEAT_LOST"
                    with self.store.lock("watch"):
                        saved = self._save_attempt(
                            self.store.read(), key, attempt, command="watch", code=EXIT_NEEDS_HUMAN
                        )
                    return self.envelope(
                        code=EXIT_NEEDS_HUMAN,
                        decision="BLOCK",
                        reason_code="HEARTBEAT_LOST",
                        next_command="handoff",
                        attempt=saved,
                        extra={"provider_error": self.store.safe(sanitize_exception(exc))},
                    )
                polls += 1
                if not until_terminal or polls >= max_polls:
                    return self.envelope(
                        code=EXIT_ACTIVE,
                        decision="ACTIVE",
                        reason_code="POLL_FAILED_WITHIN_HEARTBEAT",
                        next_command="watch --until-terminal",
                        attempt=attempt,
                    )
                self._sleep(poll_seconds)
                continue

            attempt["provider_state"] = status.state
            attempt["heartbeat_at"] = self._clock()
            attempt["progress"] = self.store.safe(status.detail)

            if status.terminal is None:
                # An unclassified provider state is never guessed in either
                # direction; a human reconciles it.
                attempt["state"] = "NEEDS_HUMAN"
                attempt["reason_code"] = "UNKNOWN_PROVIDER_STATE"
                with self.store.lock("watch"):
                    saved = self._save_attempt(
                        self.store.read(), key, attempt, command="watch", code=EXIT_NEEDS_HUMAN
                    )
                return self.envelope(
                    code=EXIT_NEEDS_HUMAN,
                    decision="BLOCK",
                    reason_code="UNKNOWN_PROVIDER_STATE",
                    next_command="handoff",
                    attempt=saved,
                )

            if status.terminal:
                attempt["state"] = "FINALIZING"
                attempt["provider_terminal_state"] = status.state
                with self.store.lock("watch"):
                    saved = self._save_attempt(self.store.read(), key, attempt, command="watch")
                return self.envelope(
                    code=EXIT_OK,
                    decision="TERMINAL",
                    reason_code=f"PROVIDER_{status.state.upper()}",
                    next_command=f"verify --example {attempt.get('example')} --seed {attempt.get('seed')}",
                    attempt=saved,
                )

            if attempt.get("state") == "SUBMITTED":
                attempt["state"] = "RUNNING"
            with self.store.lock("watch"):
                self._save_attempt(self.store.read(), key, attempt, command="watch", code=EXIT_ACTIVE)
            polls += 1
            if not until_terminal or polls >= max_polls:
                return self.envelope(
                    code=EXIT_ACTIVE,
                    decision="ACTIVE",
                    reason_code="REMOTE_JOB_RUNNING",
                    next_command="watch --until-terminal",
                    attempt=attempt,
                )
            self._sleep(poll_seconds)

    # -- verify (5.10) -------------------------------------------------------

    def verify(self, example: str, seed: int, *, phase: str = "base") -> tuple[int, dict[str, Any]]:
        with self.store.lock("verify"):
            state = self.store.read()
            key = attempt_key(example, seed, phase)
            attempt = self._attempt(state, key)
            if attempt is None:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="ATTEMPT_UNKNOWN",
                    next_command="status",
                )
            if attempt.get("state") in {"VERIFIED", "ACCEPTED", "REJECTED", "CLEANED"}:
                return self.envelope(
                    code=EXIT_OK,
                    decision="ALREADY_VERIFIED",
                    reason_code="IDEMPOTENT",
                    next_command="cleanup",
                    attempt=attempt,
                )
            reader = self._evidence_reader(str(attempt["run_id"]))
            if reader is None:
                return self.envelope(
                    code=EXIT_NEEDS_HUMAN,
                    decision="BLOCK",
                    reason_code="EVIDENCE_READER_UNAVAILABLE",
                    next_command="handoff",
                    attempt=attempt,
                )
            # The provider's terminal state decides whether incomplete evidence
            # means "training failed" or "finalization failed", so it is resolved
            # here rather than assumed from a `watch` that may have been
            # interrupted — the runbook expects watch to be re-entrant, and an
            # unrecorded state would otherwise read as a provider failure.
            terminal_state = str(attempt.get("provider_terminal_state") or "")
            if not terminal_state:
                try:
                    status = self.provider.poll(str(attempt["remote_id"]))
                except ProviderError as exc:
                    return self.envelope(
                        code=EXIT_NEEDS_HUMAN,
                        decision="BLOCK",
                        reason_code="UNKNOWN_PROVIDER_STATE",
                        next_command="handoff",
                        attempt=attempt,
                        extra={"provider_error": self.store.safe(sanitize_exception(exc))},
                    )
                if not status.terminal:
                    return self.envelope(
                        code=EXIT_ACTIVE,
                        decision="ACTIVE",
                        reason_code="JOB_STILL_ACTIVE",
                        next_command="watch --until-terminal",
                        attempt=attempt,
                    )
                terminal_state = status.state
                attempt["provider_terminal_state"] = terminal_state
                attempt["provider_state"] = terminal_state

            campaign = self.matrix.campaign
            final_seeds = campaign["final"]["seeds"]
            result = verify_run_evidence(
                reader,
                expected_matrix_digest=self.matrix.digest,
                selection_seeds=campaign["selection"]["seeds"],
                final_seeds=final_seeds,
                final_episode_count=len(final_seeds) * campaign["final"]["episodes_per_seed"],
            )
            self.store.write_json(
                self.store.evidence_path(f"verify-{key.replace(':', '-')}.json"), result.to_dict()
            )
            attempt["evidence_digest"] = _digest(result.to_dict())
            provider_completed = terminal_state.upper() in {"COMPLETED", "SUCCEEDED"}
            # A controller may cancel a provider job only after the provider has
            # remained active beyond the missing-heartbeat stop.  If the durable
            # run independently proves complete finalization, cancellation then
            # describes the stale provider record, not the training outcome.
            # This is deliberately narrower than accepting arbitrary cancelled
            # jobs: it requires the prior watchdog stop plus every evidence check.
            cancelled_after_heartbeat_stop = (
                terminal_state.upper() == "CANCELLED"
                and attempt.get("reason_code") in {"HEARTBEAT_LOST", "UNKNOWN_PROVIDER_STATE"}
            )
            if result.passed and (provider_completed or cancelled_after_heartbeat_stop):
                attempt["state"] = "VERIFIED"
                if cancelled_after_heartbeat_stop:
                    attempt["cancellation_recovery"] = {
                        "provider_terminal_state": terminal_state,
                        "prior_stop_reason": attempt.get("reason_code"),
                        "evidence_digest": attempt["evidence_digest"],
                        "at": utc_now(),
                    }
                saved = self._save_attempt(state, key, attempt, command="verify")
                return self.envelope(
                    code=EXIT_OK,
                    decision="VERIFIED",
                    reason_code=(
                        "EVIDENCE_COMPLETE_AFTER_CANCELLATION"
                        if cancelled_after_heartbeat_stop
                        else "EVIDENCE_COMPLETE"
                    ),
                    next_command="cleanup",
                    attempt=saved,
                    extra={"verification": result.to_dict()},
                )
            classifier = classify_failure(result, provider_failed=not provider_completed)
            attempt["state"] = "NEEDS_HUMAN"
            attempt["reason_code"] = classifier
            saved = self._save_attempt(state, key, attempt, command="verify", code=EXIT_REJECTED)
            return self.envelope(
                code=EXIT_REJECTED,
                decision="INCOMPLETE_EVIDENCE",
                reason_code=classifier,
                next_command="cleanup",
                attempt=saved,
                extra={"verification": result.to_dict()},
            )

    def _evidence_reader(self, run_id: str) -> EvidenceReader | None:
        if self._evidence_reader_factory is None:
            return None
        reader: EvidenceReader = self._evidence_reader_factory(run_id)
        return reader

    # -- select and extend (5.10) -------------------------------------------

    def select(self, example: str) -> tuple[int, dict[str, Any]]:
        """Rank every verified attempt of one example and decide extend vs accept."""
        with self.store.lock("select"):
            state = self.store.read()
            card = self.matrix.card(example)
            attempts = state.get("attempts") or {}

            # "An extension is allowed only by the quality decision after all
            # three base seeds." Ranking a partial set could crown an
            # unrepresentative winner and spend the single extension on it, so
            # every declared base seed must be terminal first.
            settled = {"VERIFIED", "CLEANED", "ACCEPTED", "REJECTED"}
            outstanding = sorted(
                seed
                for seed in card["seeds"]
                if (attempts.get(attempt_key(example, seed, "base")) or {}).get("state")
                not in settled
            )
            if outstanding:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="BASE_SEEDS_INCOMPLETE",
                    next_command=f"plan --example {example} --seed {outstanding[0]}",
                    extra={"outstanding_seeds": outstanding},
                )

            candidates = []
            for key, attempt in sorted(attempts.items()):
                if not isinstance(attempt, dict) or attempt.get("example") != example:
                    continue
                if attempt.get("state") not in {"VERIFIED", "CLEANED", "ACCEPTED"}:
                    continue
                reader = self._evidence_reader(str(attempt["run_id"]))
                if reader is None:
                    continue
                metrics = reader.read_json("report/metrics.json") or {}
                selected = metrics.get("selected_checkpoint")
                aggregate = metrics.get("aggregate")
                if not isinstance(selected, dict) or not isinstance(aggregate, dict):
                    continue
                candidates.append(
                    {
                        "attempt": key,
                        "run_id": attempt["run_id"],
                        "seed": attempt.get("seed"),
                        "checkpoint_sha256": selected.get("sha256"),
                        "checkpoint_native_path": selected.get("native_path"),
                        "effective_step": int(selected.get("effective_step") or 0),
                        "aggregate": aggregate,
                        "acceptance": metrics.get("acceptance"),
                    }
                )
            if not candidates:
                return self.envelope(
                    code=EXIT_NEEDS_HUMAN,
                    decision="BLOCK",
                    reason_code="NO_VERIFIED_CANDIDATES",
                    next_command="handoff",
                )
            kind = card["ranking"]["kind"]
            ordered = sorted(
                candidates,
                key=lambda item: _rank_key(item["aggregate"], kind, item["effective_step"]),
                reverse=True,
            )
            winner = ordered[0]
            preferred = winner.get("acceptance", {})
            preferred_passed = bool(
                isinstance(preferred, dict)
                and isinstance(preferred.get("preferred"), dict)
                and preferred["preferred"].get("passed")
            )
            examples = state.setdefault("examples", {})
            record = examples.setdefault(example, {})
            record["selection"] = {
                "run_id": winner["run_id"],
                "seed": winner["seed"],
                "checkpoint_sha256": winner["checkpoint_sha256"],
                "checkpoint_native_path": winner["checkpoint_native_path"],
                "effective_step": winner["effective_step"],
                "runner_up": ordered[1]["run_id"] if len(ordered) > 1 else None,
                "candidate_count": len(ordered),
                "preferred_passed": preferred_passed,
                "at": utc_now(),
            }
            extension_available = (
                card.get("extension_steps") is not None
                and not record.get("extension_consumed", False)
            )
            if preferred_passed:
                record["selection"]["decision"] = "EXTENSION_SKIPPED_QUALITY_MET"
                next_command = f"accept --example {example}"
            elif extension_available:
                record["selection"]["decision"] = "EXTENSION_REQUIRED"
                next_command = f"plan --example {example} --seed {winner['seed']} --phase extension"
            else:
                record["selection"]["decision"] = "NO_EXTENSION_REMAINING"
                next_command = f"accept --example {example}"
            self.store.write(state)
            self.store.journal(
                {"command": "select", "example": example, "after": record["selection"]["decision"]}
            )
            return self.envelope(
                code=EXIT_OK,
                decision=record["selection"]["decision"],
                reason_code="SELECTION_RECORDED",
                next_command=next_command,
                extra={"selection": record["selection"]},
            )

    def extend(self, example: str, confirmation: str) -> tuple[int, dict[str, Any]]:
        with self.store.lock("extend"):
            state = self.store.read()
            record = (state.get("examples") or {}).get(example) or {}
            if record.get("extension_consumed"):
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="EXTENSION_ALREADY_CONSUMED",
                    next_command=f"accept --example {example}",
                )
            selection = record.get("selection")
            if not isinstance(selection, dict):
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="SELECTION_REQUIRED",
                    next_command=f"select --example {example}",
                )
            plan = self.build_plan(example, int(selection["seed"]), phase="extension")
            if confirmation != plan["plan_digest"]:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="PLAN_DIGEST_MISMATCH",
                    next_command=f"plan --example {example} --seed {selection['seed']} --phase extension",
                )
            record["extension_consumed"] = True
            state.setdefault("examples", {})[example] = record
            self.store.write(state)
            self.store.journal({"command": "extend", "example": example, "after": "EXTENSION_AUTHORIZED"})
            return self.envelope(
                code=EXIT_OK,
                decision="EXTENSION_AUTHORIZED",
                reason_code="SINGLE_EXTENSION_CONSUMED",
                next_command=f"submit --example {example} --seed {selection['seed']} --phase extension --confirm-plan-digest {plan['plan_digest']}",
            )

    # -- accept (5.10) -------------------------------------------------------

    def accept(self, example: str) -> tuple[int, dict[str, Any]]:
        with self.store.lock("accept"):
            state = self.store.read()
            record = (state.get("examples") or {}).get(example) or {}
            selection = record.get("selection")
            if not isinstance(selection, dict):
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="SELECTION_REQUIRED",
                    next_command=f"select --example {example}",
                )
            reader = self._evidence_reader(str(selection["run_id"]))
            metrics = (reader.read_json("report/metrics.json") if reader else None) or {}
            acceptance = metrics.get("acceptance") or {}
            hard = bool(isinstance(acceptance.get("hard"), dict) and acceptance["hard"].get("passed"))
            preferred = bool(
                isinstance(acceptance.get("preferred"), dict) and acceptance["preferred"].get("passed")
            )
            cleanup_ok = all(
                item.get("cleanup_state") == "PASS"
                for item in (state.get("attempts") or {}).values()
                if isinstance(item, dict) and item.get("example") == example
            )
            outcome = {
                "example": example,
                "hard_gate": hard,
                "preferred_target": preferred,
                "cleanup_state": "PASS" if cleanup_ok else "INCOMPLETE",
                "run_id": selection["run_id"],
                "checkpoint_sha256": selection["checkpoint_sha256"],
                "at": utc_now(),
            }
            if not hard:
                decision, code, reason = "REJECTED", EXIT_REJECTED, "REJECTED_HARD_GATE"
            elif not preferred:
                decision, code, reason = "NEEDS_HUMAN", EXIT_NEEDS_HUMAN, "NEEDS_HUMAN_QUALITY_TARGET"
            elif not cleanup_ok:
                decision, code, reason = "NEEDS_HUMAN", EXIT_NEEDS_HUMAN, "CLEANUP_REQUIRED"
            else:
                decision, code, reason = "ACCEPTED", EXIT_OK, "ACCEPTED_AND_PIN_READY"
            outcome["decision"] = decision
            record["acceptance"] = outcome
            state.setdefault("examples", {})[example] = record
            self.store.write(state)
            self.store.write_json(self.store.evidence_path(f"accept-{example}.json"), outcome)
            self.store.journal({"command": "accept", "example": example, "after": decision})
            return self.envelope(
                code=code,
                decision=decision,
                reason_code=reason,
                next_command="audit-cloud" if decision == "ACCEPTED" else "handoff",
                extra={"acceptance": outcome},
            )

    # -- cleanup and audit (5.10) -------------------------------------------

    def cleanup(self) -> tuple[int, dict[str, Any]]:
        with self.store.lock("cleanup"):
            state = self.store.read()
            try:
                audit = self.provider.audit()
            except ProviderError as exc:
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="CLEANUP_AUDIT_FAILED",
                    next_command="handoff",
                    extra={"provider_error": self.store.safe(sanitize_exception(exc))},
                )
            known_remote = {
                item.get("remote_id")
                for item in (state.get("attempts") or {}).values()
                if isinstance(item, dict)
            }
            unaccounted = [
                job for job in audit.get("active_jobs", []) if job and job not in known_remote
            ]
            unaccounted_instances = self._unaccounted_running(audit)
            cleanup_state = "PASS" if not unaccounted and not unaccounted_instances else "BLOCKED"
            self.store.write_json(
                self.store.audit_path("cleanup.json"),
                {
                    "audit": audit,
                    "unaccounted_jobs": unaccounted,
                    "unaccounted_instances": unaccounted_instances,
                    "expected_running_instances": sorted(self._expected_running_instances()),
                    "cleanup_state": cleanup_state,
                },
            )
            for key, attempt in sorted((state.get("attempts") or {}).items()):
                if not isinstance(attempt, dict):
                    continue
                if attempt.get("state") in {"VERIFIED", "ACCEPTED", "REJECTED", "NEEDS_HUMAN"}:
                    attempt["cleanup_state"] = cleanup_state
                    if cleanup_state == "PASS" and attempt.get("state") == "VERIFIED":
                        attempt["state"] = "CLEANED"
                    state["attempts"][key] = attempt
            self.store.write(state)
            self.store.journal({"command": "cleanup", "after": cleanup_state})
            if cleanup_state != "PASS":
                return self.envelope(
                    code=EXIT_INVARIANT,
                    decision="BLOCK",
                    reason_code="UNACCOUNTED_RESOURCE",
                    next_command="handoff",
                    extra={
                        "unaccounted_jobs": unaccounted,
                        "unaccounted_instances": unaccounted_instances,
                        "audit": audit,
                    },
                )
            return self.envelope(
                code=EXIT_OK,
                decision="CLEANED",
                reason_code="CLEANUP_PASS",
                next_command="status",
                extra={"audit": audit},
            )

    def audit_cloud(self) -> tuple[int, dict[str, Any]]:
        try:
            audit = self.provider.audit()
        except ProviderError as exc:
            return self.envelope(
                code=EXIT_INVARIANT,
                decision="BLOCK",
                reason_code="AUDIT_FAILED",
                next_command="handoff",
                extra={"provider_error": self.store.safe(sanitize_exception(exc))},
            )
        unaccounted_instances = self._unaccounted_running(audit)
        expected = sorted(self._expected_running_instances())
        self.store.write_json(
            self.store.audit_path("cloud.json"),
            {
                "audit": audit,
                "at": utc_now(),
                "expected_running_instances": expected,
                "unaccounted_instances": unaccounted_instances,
            },
        )
        clean = not audit.get("active_jobs") and not unaccounted_instances
        return self.envelope(
            code=EXIT_OK if clean else EXIT_INVARIANT,
            decision="CLEAN" if clean else "UNACCOUNTED_RESOURCE",
            reason_code="CLOUD_AUDIT",
            next_command="status" if clean else "handoff",
            extra={
                "audit": audit,
                "expected_running_instances": expected,
                "unaccounted_instances": unaccounted_instances,
            },
        )

    # -- status and handoff (5.10) ------------------------------------------

    def status(self) -> tuple[int, dict[str, Any]]:
        state = self.store.read()
        active = active_attempt(state)
        attempts = {
            key: {
                "state": item.get("state"),
                "cleanup_state": item.get("cleanup_state"),
                "reason_code": item.get("reason_code"),
            }
            for key, item in sorted((state.get("attempts") or {}).items())
            if isinstance(item, dict)
        }
        if active is not None:
            next_command = "watch --until-terminal"
            code, decision = EXIT_ACTIVE, "ACTIVE"
        elif (state.get("implementation_gate") or {}).get("decision") != "PASS":
            next_command, code, decision = "implementation-gate", EXIT_OK, "STATUS"
        else:
            next_command, code, decision = "preflight", EXIT_OK, "STATUS"
        return self.envelope(
            code=code,
            decision=decision,
            reason_code="STATE_READ",
            next_command=next_command,
            attempt=active,
            extra={"attempts": attempts, "examples": state.get("examples", {})},
        )

    def handoff(self, *, fmt: str = "markdown") -> tuple[int, dict[str, Any]]:
        state = self.store.read()
        active = active_attempt(state) or {}
        summary = {
            "campaign_id": self.store.campaign_id,
            "matrix_digest": state.get("matrix_digest"),
            "revision": (state.get("location_attestation") or {}).get("immutable_revision"),
            "current_attempt": active.get("key"),
            "state": active.get("state") or state.get("state"),
            "reason_code": active.get("reason_code"),
            "remote_id": active.get("remote_id"),
            "provider_state": active.get("provider_state"),
            "evidence_digest": active.get("evidence_digest"),
            "cleanup_state": active.get("cleanup_state", "not_started"),
            "examples": state.get("examples", {}),
        }
        if fmt == "markdown":
            lines = [
                "## Campaign handoff",
                f"- Campaign ID: {summary['campaign_id']}",
                f"- Matrix digest: {summary['matrix_digest']}",
                f"- Repository revision / image digests: {summary['revision']}",
                f"- Current example / seed / attempt: {summary['current_attempt']}",
                f"- State and reason code: {summary['state']} / {summary['reason_code']}",
                f"- Remote job ID and provider state: {summary['remote_id']} / {summary['provider_state']}",
                f"- Effective steps / last durable checkpoint digest: {active.get('progress')}",
                f"- Verified artifacts / missing artifacts: {summary['evidence_digest']}",
                f"- Selection or acceptance result: {json.dumps(summary['examples'], sort_keys=True)}",
                f"- Cleanup audit result: {summary['cleanup_state']}",
                f"- Retries and extensions already consumed: {active.get('retries_consumed', 0)}",
                f"- Exact next command, or NEEDS_HUMAN: {self.status()[1]['next_command']}",
                "- Safe operator note: this report contains no credentials or secret selectors.",
            ]
            self.store.write_text(self.store.handoff_path, "\n".join(lines) + "\n")
        return self.envelope(
            code=EXIT_OK,
            decision="HANDOFF",
            reason_code="REPORT_WRITTEN",
            next_command=self.status()[1]["next_command"],
            extra={"handoff": summary},
        )

    # -- stale lock recovery (5.11) -----------------------------------------

    def recover_lock(self) -> tuple[int, dict[str, Any]]:
        """Clear a lock only after proving its holder is gone. Changes no remote state."""
        holder = self.store.lock_holder()
        if not self.store.lock_path.exists():
            return self.envelope(
                code=EXIT_OK,
                decision="NO_LOCK",
                reason_code="IDEMPOTENT",
                next_command="status",
            )
        pid = holder.get("pid")
        hostname = holder.get("hostname")
        if hostname != socket.gethostname():
            # Liveness of a process on another host is unprovable from here.
            return self.envelope(
                code=EXIT_INVARIANT,
                decision="BLOCK",
                reason_code="LOCK_HOLDER_ON_ANOTHER_HOST",
                next_command="handoff",
                extra={"holder": {"hostname": hostname}},
            )
        if isinstance(pid, int) and process_is_live(pid):
            return self.envelope(
                code=EXIT_INVARIANT,
                decision="BLOCK",
                reason_code="LOCK_HOLDER_IS_LIVE",
                next_command="watch --until-terminal",
                extra={"holder": {"pid": pid}},
            )
        self.store.lock_path.unlink(missing_ok=True)
        self.store.journal({"command": "recover-lock", "after": "LOCK_CLEARED"})
        return self.envelope(
            code=EXIT_OK,
            decision="LOCK_CLEARED",
            reason_code="HOLDER_NOT_LIVE",
            next_command="status",
        )


# -- CLI ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nebius-only curated showcase campaign controller")
    parser.add_argument(
        "command",
        choices=(
            "init", "implementation-gate", "preflight", "plan", "submit", "watch",
            "verify", "select", "extend", "accept", "cleanup", "audit-cloud",
            "status", "handoff", "recover-lock",
        ),
    )
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--matrix", default="configs/showcase_training_matrix.yaml")
    parser.add_argument("--state-root", type=Path, default=Path(".showcase-campaigns"))
    parser.add_argument("--example")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--phase", choices=("base", "extension"), default="base")
    parser.add_argument("--confirm-plan-digest")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--until-terminal", action="store_true")
    return parser


def dispatch(campaign: Campaign, args: argparse.Namespace, attestation: LocationAttestation) -> tuple[int, dict[str, Any]]:
    command = args.command
    if command == "init":
        return campaign.initialize(attestation)
    if command == "implementation-gate":
        return campaign.implementation_gate()
    if command == "preflight":
        return campaign.preflight(args.example)
    if command == "plan":
        if args.example is None or args.seed is None:
            raise CampaignError("plan requires --example and --seed")
        return campaign.plan(args.example, args.seed, phase=args.phase)
    if command == "submit":
        if args.example is None or args.seed is None or args.confirm_plan_digest is None:
            raise CampaignError("submit requires --example, --seed, and --confirm-plan-digest")
        return campaign.submit(args.example, args.seed, args.confirm_plan_digest, phase=args.phase)
    if command == "watch":
        return campaign.watch(poll_seconds=args.poll_seconds, until_terminal=args.until_terminal)
    if command == "verify":
        if args.example is None or args.seed is None:
            raise CampaignError("verify requires --example and --seed")
        return campaign.verify(args.example, args.seed, phase=args.phase)
    if command == "select":
        if args.example is None:
            raise CampaignError("select requires --example")
        return campaign.select(args.example)
    if command == "extend":
        if args.example is None or args.confirm_plan_digest is None:
            raise CampaignError("extend requires --example and --confirm-plan-digest")
        return campaign.extend(args.example, args.confirm_plan_digest)
    if command == "accept":
        if args.example is None:
            raise CampaignError("accept requires --example")
        return campaign.accept(args.example)
    if command == "cleanup":
        return campaign.cleanup()
    if command == "audit-cloud":
        return campaign.audit_cloud()
    if command == "status":
        return campaign.status()
    if command == "handoff":
        return campaign.handoff(fmt=args.format)
    if command == "recover-lock":
        return campaign.recover_lock()
    raise CampaignError(f"unhandled command: {command}")


def evidence_reader_factory_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Any:
    """Build prefix-bound readers over the campaign's durable artifact bucket.

    `verify` runs on the orchestration VM and must read what the job published,
    so the reader is constructed from the same non-secret destination the plan
    records. Object credentials come from the VM's own configured chain, never
    from the campaign state. Without a destination there is no reader, and
    `verify` blocks rather than reporting an unverified run as verified.
    """
    source = os.environ if environment is None else environment
    bucket = source.get("SIM2POLICY_ARTIFACT_BUCKET", "")
    if not bucket:
        return None
    config = StorageConfig(
        mode="s3",
        bucket=bucket,
        endpoint_url=source.get("SIM2POLICY_ARTIFACT_ENDPOINT") or None,
        region=source.get("SIM2POLICY_ARTIFACT_REGION") or None,
    )

    def factory(run_id: str) -> EvidenceReader:
        # Imported here so the CLI stays importable, and every other command
        # stays usable, on a host without the object-storage dependency.
        from sim2policy.storage import ArtifactStore

        return ArtifactStoreEvidenceReader(ArtifactStore(config, run_id))

    return factory


def main(argv: Sequence[str] | None = None) -> None:
    try:
        attestation = require_nebius_execution("campaign")
        args = build_parser().parse_args(argv)
        matrix = load_matrix(args.matrix)
        store = CampaignStore(args.state_root, args.campaign_id)
        campaign = Campaign(
            store,
            matrix,
            provider=provider_from_environment(),
            evidence_reader_factory=evidence_reader_factory_from_environment(),
        )
        code, result = dispatch(campaign, args, attestation)
    except (CampaignError, MatrixError, ExecutionLocationError) as exc:
        # The message is redacted before printing: a matrix or path error can
        # carry an environment-derived value.
        code = EXIT_INVARIANT
        result = {
            "decision": "BLOCK",
            "reason_code": sanitize_exception(exc),
            "next_command": "handoff",
        }
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
