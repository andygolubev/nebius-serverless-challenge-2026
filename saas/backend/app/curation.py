"""Typed, allowlisted curated evidence for the public showcase.

The showcase serves anonymous traffic from artifacts a training job wrote, so the
boundary between "what the run recorded" and "what the public sees" has to be
explicit rather than incidental. This module is that boundary.

Two rules define it:

* **Allowlist, not denylist.** `CuratedEvidence` names every field that may become
  public. A field the training runtime adds later is private until someone edits
  this file, which is the safe default for a surface with no authentication.
* **Fail closed.** Every normalizer returns `None` (or raises `CurationError`)
  rather than guessing. An ambiguous `success.met`, an unrecognized environment
  identity, or a mutable image tag withholds the entry instead of publishing a
  claim the evidence does not support.

Curation runs in two modes. Publication gates what may be *served* from an
already-reviewed pin. Promotion additionally gates what may *become* a pin, adding
the checks that only make sense once — duplicate pins, cleanup proof, and the
preferred-quality target.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Runtime environment identities, never friendly card labels. A curated run may not
# choose its own identity string: it must match the server-owned value exactly, so a
# stale card cannot advertise a task its pinned run did not execute.
CANONICAL_ENVIRONMENTS: dict[str, str] = {
    "reacher-target": "Reacher-v5",
    "halfcheetah-sprint": "HalfCheetah-v5",
    "ant-explorer": "Ant-v5",
    "hopper-balance": "Hopper-v5",
    "walker2d-stride": "Walker2d-v5",
    "go1-walker": "Go1JoystickFlatTerrain",
    "g1-rough-terrain": "G1ForwardRoughTerrain",
}

# The runtime each example is expected to have executed. Checked alongside the
# environment identity so a stale card cannot advertise a backend its pinned run
# did not use.
CANONICAL_BACKENDS: dict[str, str] = {
    "reacher-target": "sb3",
    "halfcheetah-sprint": "sb3",
    "ant-explorer": "sb3",
    "hopper-balance": "sb3",
    "walker2d-stride": "sb3",
    "go1-walker": "mjx",
    "g1-rough-terrain": "mjx",
}

# Numeric evaluation fields that may be published. Explicit so an aggregate key the
# evaluator adds later stays private until it is reviewed here.
AGGREGATE_FIELDS = frozenset(
    {
        "mean_reward",
        "std_reward",
        "mean_episode_length",
        "episodes",
        "mean_velocity",
        "min_velocity",
        "no_fall_count",
    }
)

# Identities a curriculum phase may legitimately record. G1 acquires a flat gait
# before rough terrain, so `G1ForwardFlatTerrain` is a valid *phase* identity while
# never being a valid *final task* identity — public success is scored only against
# the rough-terrain gate.
CANONICAL_PHASE_ENVIRONMENTS: dict[str, frozenset[str]] = {
    "g1-rough-terrain": frozenset({"G1ForwardFlatTerrain", "G1ForwardRoughTerrain"}),
}

# A tenant job id is `uuid4().hex`. A curated run must never be mistakable for one.
TENANT_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
PENDING_RUN_PREFIX = "pending-curated-run-"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# An immutable image reference pins a digest. A bare tag can be moved after review.
IMMUTABLE_IMAGE_RE = re.compile(r"@sha256:[0-9a-f]{64}$")

# Criterion strings the evaluator emits, parsed to cross-check the recorded verdict
# against the recorded numbers. An unparseable criterion is not fatal; a criterion
# that parses and *disagrees* with `met` is.
_THRESHOLD_CRITERION = re.compile(r"^(?P<metric>[a-z_]+)\s*>=\s*(?P<threshold>-?\d+(?:\.\d+)?)$")

# Historical runs retained as named comparison baselines and rollback targets. They
# are deliberately not pinnable: reaching for one instead of a fresh campaign result
# is a reviewed decision, never an automatic fallback.
HISTORICAL_BASELINES: dict[str, dict[str, Any]] = {
    "go1-walker": {"label": "go1-mjx-quality-100m", "mean_velocity": 0.9653, "note": "20/20 no-fall at 100M"},
    "halfcheetah-sprint": {"label": "halfcheetah-gallery-v1", "mean_reward": 1672.368},
    "ant-explorer": {"label": "ant-gallery-v1", "mean_reward": 2869.711},
    "hopper-balance": {"label": "hopper-gallery-v1", "mean_reward": 1562.019},
    "walker2d-stride": {"label": "walker2d-gallery-v1", "mean_reward": 3812.003},
    "reacher-target": {"label": "reacher-gallery-v1", "mean_reward": -7.779},
}


class CurationError(ValueError):
    """Raised when evidence cannot be normalized unambiguously."""


@dataclass(frozen=True)
class SelectedCheckpoint:
    effective_step: int
    sha256: str


@dataclass(frozen=True)
class AcceptanceOutcome:
    hard_passed: bool
    preferred_passed: bool


@dataclass(frozen=True)
class PhaseLineage:
    environment: str
    effective_steps: int | None
    outcome: str | None
    input_checkpoint_sha256: str | None = None
    output_checkpoint_sha256: str | None = None


@dataclass(frozen=True)
class ProgressionEntry:
    stage: str
    effective_step: int
    checkpoint_sha256: str
    selected: bool
    regression: bool
    video: str | None


@dataclass(frozen=True)
class CuratedEvidence:
    """Everything, and only what, the public surface may show for one example."""

    example_id: str
    environment: str
    backend: str
    matrix_digest: str
    image_reference: str
    checkpoint: str | None
    selected_checkpoint: SelectedCheckpoint
    success: bool
    criterion: str
    primary_metric: float | None
    aggregate: dict[str, float]
    acceptance: AcceptanceOutcome
    measured_runtime_seconds: float | None
    measured_cost: float | None
    rate_date: str | None
    total_timesteps: int | None
    platform: str | None
    preset: str | None
    seed_roles: dict[str, list[int]] = field(default_factory=dict)
    ranking_explanation: dict[str, Any] = field(default_factory=dict)
    progression: tuple[ProgressionEntry, ...] = ()
    phases: tuple[PhaseLineage, ...] = ()
    runtime_versions: dict[str, str] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize the allowlist. No field reaches the public surface by accident."""
        return asdict(self)


def normalize_success(metrics: Any) -> dict[str, Any] | None:
    """Accept only a recognized `success` shape; reject ambiguity rather than guess.

    Rejects a missing block, extra keys (an unrecognized legacy shape), a non-boolean
    verdict, and a verdict that contradicts its own parseable threshold. Returning
    `None` withholds the entry; it never downgrades to a default.
    """
    if not isinstance(metrics, dict):
        return None
    success = metrics.get("success")
    if not isinstance(success, dict) or set(success) != {"met", "criterion"}:
        return None
    met = success.get("met")
    criterion = success.get("criterion")
    if not isinstance(met, bool) or not isinstance(criterion, str) or not criterion:
        return None

    # Cross-check a parseable threshold criterion against the recorded aggregate.
    # A run claiming success while its own numbers say otherwise is contradictory
    # evidence, not a passing run.
    match = _THRESHOLD_CRITERION.match(criterion.strip())
    aggregate = metrics.get("aggregate")
    if match and isinstance(aggregate, dict):
        metric_name = match.group("metric")
        recorded = aggregate.get(metric_name)
        if isinstance(recorded, (int, float)) and not isinstance(recorded, bool):
            if met is not (float(recorded) >= float(match.group("threshold"))):
                return None
    return {"met": met, "criterion": criterion}


def _progression(value: Any) -> tuple[ProgressionEntry, ...]:
    if not isinstance(value, list) or not value:
        raise CurationError("progression evidence is missing")
    entries: list[ProgressionEntry] = []
    for item in value:
        if not isinstance(item, dict):
            raise CurationError("progression entry is malformed")
        checkpoint = item.get("checkpoint")
        if not isinstance(checkpoint, dict):
            raise CurationError("progression entry has no checkpoint record")
        digest = checkpoint.get("sha256")
        step = checkpoint.get("effective_step")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise CurationError("progression checkpoint digest is invalid")
        if isinstance(step, bool) or not isinstance(step, int):
            raise CurationError("progression checkpoint step is invalid")
        entries.append(
            ProgressionEntry(
                stage=str(item.get("stage", "")),
                effective_step=step,
                checkpoint_sha256=digest,
                selected=item.get("selected") is True,
                # Regression is surfaced, never smoothed away: a later checkpoint
                # that lost to an earlier one stays visible in the public record.
                regression=item.get("regression") is True,
                video=item.get("video") if isinstance(item.get("video"), str) else None,
            )
        )
    if not any(entry.selected for entry in entries):
        raise CurationError("progression does not identify the selected policy")
    return tuple(entries)


def _phases(value: Any, example_id: str) -> tuple[PhaseLineage, ...]:
    if not isinstance(value, dict):
        return ()
    allowed = CANONICAL_PHASE_ENVIRONMENTS.get(example_id)
    phases: list[PhaseLineage] = []
    for name in ("flat", "rough"):
        phase = value.get(name)
        if not isinstance(phase, dict):
            continue
        environment = phase.get("environment")
        if allowed is not None and environment not in allowed:
            raise CurationError(f"phase {name} records an unrecognized environment identity")
        phases.append(
            PhaseLineage(
                environment=str(environment),
                effective_steps=phase.get("effective_steps")
                if isinstance(phase.get("effective_steps"), int)
                else None,
                outcome=str(phase["outcome"]) if isinstance(phase.get("outcome"), str) else None,
                input_checkpoint_sha256=phase.get("input_checkpoint_digest")
                if isinstance(phase.get("input_checkpoint_digest"), str)
                else None,
                output_checkpoint_sha256=phase.get("output_checkpoint_digest")
                if isinstance(phase.get("output_checkpoint_digest"), str)
                else None,
            )
        )
    return tuple(phases)


def validate_run_identity(run_id: str, *, known_pins: dict[str, str] | None = None, example_id: str = "") -> None:
    """Reject a pin that is tenant-shaped, a placeholder, or claimed twice."""
    if not run_id:
        raise CurationError("pinned run identity is empty")
    if run_id.startswith(PENDING_RUN_PREFIX):
        raise CurationError("pinned run is still a placeholder")
    if TENANT_JOB_ID_RE.fullmatch(run_id):
        raise CurationError("pinned run identity collides with the tenant job space")
    if "/" in run_id or ".." in run_id.split("."):
        raise CurationError("pinned run identity is not a single safe path segment")
    if known_pins:
        claimants = [key for key, value in known_pins.items() if value == run_id and key != example_id]
        if claimants:
            raise CurationError("pinned run identity is claimed by another example")


def curate(
    example_id: str,
    metrics: Any,
    *,
    run_id: str = "",
    promotion: bool = False,
    cleanup_state: str | None = None,
    known_pins: dict[str, str] | None = None,
) -> CuratedEvidence:
    """Normalize one curated run into the public allowlist, or raise.

    `promotion=True` adds the checks that gate *becoming* a pin rather than being
    served as one: the preferred quality target, proof that chargeable resources
    were cleaned up, and pin uniqueness.
    """
    if example_id not in CANONICAL_ENVIRONMENTS:
        raise CurationError("unknown showcase example")
    if not isinstance(metrics, dict) or not metrics:
        raise CurationError("curated run recorded no metrics")
    if promotion or run_id:
        validate_run_identity(run_id, known_pins=known_pins, example_id=example_id)

    environment = metrics.get("environment")
    if environment != CANONICAL_ENVIRONMENTS[example_id]:
        raise CurationError("recorded environment is not the canonical identity for this example")

    backend = metrics.get("backend")
    if backend not in {"sb3", "mjx"}:
        raise CurationError("recorded backend is not a known runtime")
    if backend != CANONICAL_BACKENDS[example_id]:
        raise CurationError("recorded backend disagrees with the declared example")

    success = normalize_success(metrics)
    if success is None:
        raise CurationError("task success could not be normalized unambiguously")
    if not success["met"]:
        # Artifact completeness is not achievement: a finished run below its gate
        # stays diagnostic evidence.
        raise CurationError("curated run did not meet its task gate")

    matrix_digest = metrics.get("matrix_digest")
    if not isinstance(matrix_digest, str) or not SHA256_RE.fullmatch(matrix_digest):
        raise CurationError("campaign matrix digest is missing or invalid")

    selected = metrics.get("selected_checkpoint")
    if not isinstance(selected, dict):
        raise CurationError("selected checkpoint evidence is missing")
    digest = selected.get("sha256")
    step = selected.get("effective_step")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise CurationError("selected checkpoint digest is invalid")
    if isinstance(step, bool) or not isinstance(step, int):
        raise CurationError("selected checkpoint step is invalid")

    resolved = metrics.get("resolved_config")
    if not isinstance(resolved, dict):
        raise CurationError("resolved configuration evidence is missing")
    image = resolved.get("runtime_image")
    if not isinstance(image, str) or not IMMUTABLE_IMAGE_RE.search(image):
        raise CurationError("runtime image is not pinned to an immutable digest")

    benchmark = metrics.get("benchmark")
    if not isinstance(benchmark, dict):
        raise CurationError("measured benchmark evidence is missing")
    cost = benchmark.get("estimated_cost")
    runtime_seconds = metrics.get("runtime_seconds")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool):
        raise CurationError("measured cost evidence is missing")
    if not isinstance(runtime_seconds, (int, float)) or isinstance(runtime_seconds, bool):
        raise CurationError("measured runtime evidence is missing")

    acceptance_raw = metrics.get("acceptance")
    if not isinstance(acceptance_raw, dict):
        raise CurationError("hard/preferred acceptance evidence is missing")
    hard = acceptance_raw.get("hard")
    preferred = acceptance_raw.get("preferred")
    if not isinstance(hard, dict) or not isinstance(preferred, dict):
        raise CurationError("acceptance evidence is malformed")
    acceptance = AcceptanceOutcome(
        hard_passed=hard.get("passed") is True,
        preferred_passed=preferred.get("passed") is True,
    )
    if not acceptance.hard_passed:
        raise CurationError("curated run failed its hard acceptance floor")

    progression = _progression(metrics.get("progression"))
    if not any(entry.checkpoint_sha256 == digest and entry.selected for entry in progression):
        raise CurationError("progression does not link to the selected checkpoint")

    seed_roles_raw = metrics.get("seed_roles")
    seed_roles: dict[str, list[int]] = {}
    if isinstance(seed_roles_raw, dict):
        selection = [int(v) for v in seed_roles_raw.get("selection", []) if isinstance(v, int)]
        final = [int(v) for v in seed_roles_raw.get("final", []) if isinstance(v, int)]
        if not selection or not final or set(selection) & set(final):
            raise CurationError("selection and final seed roles are missing or overlap")
        seed_roles = {"selection": selection, "final": final}
    elif promotion:
        raise CurationError("seed role evidence is missing")

    if promotion:
        if not acceptance.preferred_passed:
            raise CurationError("curated run missed its preferred quality target")
        if cleanup_state != "PASS":
            raise CurationError("cleanup proof is missing for this curated run")

    raw_aggregate = metrics.get("aggregate") if isinstance(metrics.get("aggregate"), dict) else {}
    aggregate = {
        str(key): float(value)
        for key, value in raw_aggregate.items()
        if key in AGGREGATE_FIELDS and isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    primary = aggregate.get("mean_velocity", aggregate.get("mean_reward"))
    training = resolved.get("training") if isinstance(resolved.get("training"), dict) else {}
    hardware = resolved.get("hardware") if isinstance(resolved.get("hardware"), dict) else {}
    versions_raw = metrics.get("versions")
    versions = (
        {str(k): str(v) for k, v in versions_raw.items()} if isinstance(versions_raw, dict) else {}
    )

    return CuratedEvidence(
        example_id=example_id,
        environment=str(environment),
        backend=str(backend),
        matrix_digest=matrix_digest,
        image_reference=image,
        # The native checkpoint *filename*, never an object key or storage path.
        checkpoint=str(metrics["checkpoint"]) if isinstance(metrics.get("checkpoint"), str) else None,
        selected_checkpoint=SelectedCheckpoint(effective_step=step, sha256=digest),
        success=True,
        criterion=success["criterion"],
        primary_metric=float(primary) if isinstance(primary, (int, float)) and not isinstance(primary, bool) else None,
        aggregate=aggregate,
        acceptance=acceptance,
        measured_runtime_seconds=float(runtime_seconds),
        measured_cost=float(cost),
        rate_date=str(benchmark["rate_date"]) if isinstance(benchmark.get("rate_date"), str) else None,
        total_timesteps=training.get("total_steps") if isinstance(training.get("total_steps"), int) else None,
        platform=str(hardware["platform"]) if isinstance(hardware.get("platform"), str) else None,
        preset=str(hardware["preset"]) if isinstance(hardware.get("preset"), str) else None,
        seed_roles=seed_roles,
        ranking_explanation=metrics.get("ranking_explanation")
        if isinstance(metrics.get("ranking_explanation"), dict)
        else {},
        progression=progression,
        phases=_phases(metrics.get("phase_lineage"), example_id),
        runtime_versions=versions,
    )
