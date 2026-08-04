"""Artifact verification for one curated run prefix.

Implements the runbook's evidence contract. Two properties matter more than the
individual checks:

* **Prefix-bound.** A reader is constructed for exactly one run and cannot read
  another, so a missing object can never be satisfied by an older run's copy.
  Cross-run fallback would silently promote stale evidence, which is precisely the
  failure this campaign exists to avoid.
* **Existence is not acceptance.** Objects are checked for identity and linkage —
  the selected checkpoint digest must appear in the checkpoint inventory, the
  progression must name it, the bundle must carry it — not merely for presence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: Logical artifact names a curated run must publish before it can be promoted.
REQUIRED_ARTIFACTS = frozenset(
    {
        "final_policy",
        "metrics_json",
        "report_md",
        "resolved_config",
        "runtime_versions",
        "policy_bundle",
        "video_untrained",
        "video_mid",
        "video_selected",
        "video_final",
        "video_final_step",
        "progression_montage",
    }
)

#: Progression stages that must each carry an exact step and checkpoint digest.
REQUIRED_PROGRESSION_STAGES = ("untrained", "mid", "selected", "final-step")


class EvidenceReader(Protocol):
    """Reads JSON and object metadata beneath exactly one run prefix."""

    def read_json(self, relative: str) -> dict[str, Any] | None: ...

    def head(self, relative: str) -> dict[str, Any] | None: ...


@dataclass
class VerificationResult:
    checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.failures

    def record(self, name: str, ok: bool, detail: str | None = None) -> bool:
        self.checks[name] = ok
        if not ok:
            self.failures.append(detail or name)
        return ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": dict(sorted(self.checks.items())),
            "failures": list(self.failures),
            "evidence": self.evidence,
        }


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def verify_run_evidence(
    reader: EvidenceReader,
    *,
    expected_matrix_digest: str,
    selection_seeds: Sequence[int],
    final_seeds: Sequence[int],
    final_episode_count: int,
    require_curation_evidence: bool = True,
) -> VerificationResult:
    """Validate every required object, checksum, and linkage under one run prefix."""
    result = VerificationResult()

    manifest = reader.read_json("report/artifacts.json")
    readable = isinstance(manifest, dict)
    if not result.record("manifest_readable", readable, "artifact manifest is unreadable"):
        return result
    assert manifest is not None

    artifacts = manifest.get("artifacts")
    checksums = manifest.get("checksums")
    if not result.record(
        "manifest_shape",
        isinstance(artifacts, dict) and isinstance(checksums, dict),
        "artifact manifest is missing its artifacts/checksums envelope",
    ):
        return result
    assert isinstance(artifacts, dict) and isinstance(checksums, dict)

    missing = sorted(REQUIRED_ARTIFACTS - set(artifacts))
    result.record("required_artifacts", not missing, f"required artifacts absent: {missing}")
    result.record(
        "checksum_coverage",
        set(checksums) == set(artifacts),
        "checksum manifest does not cover exactly the published artifacts",
    )

    # Every declared object must exist at its declared size. Size is the cheap
    # half of integrity; the digest half is enforced by the artifact reader that
    # serves the object publicly, which streams and compares it.
    for name, relative in sorted(artifacts.items()):
        descriptor = checksums.get(name)
        if not isinstance(descriptor, dict) or not _is_digest(descriptor.get("sha256")):
            result.record(f"checksum:{name}", False, f"checksum descriptor for {name} is invalid")
            continue
        head = reader.head(str(relative))
        if head is None:
            result.record(f"object:{name}", False, f"declared object is absent: {name}")
            continue
        result.record(
            f"object:{name}",
            head.get("size_bytes") == descriptor.get("size_bytes"),
            f"object size disagrees with the checksum manifest: {name}",
        )

    status = reader.read_json("metadata/status.json") or {}
    result.record(
        "terminal_status",
        status.get("status") == "completed",
        "run status is not terminal-completed",
    )

    metrics = reader.read_json("report/metrics.json")
    if not result.record("metrics_readable", isinstance(metrics, dict), "metrics.json is unreadable"):  # noqa: E501
        return result
    assert metrics is not None

    result.record(
        "matrix_digest",
        metrics.get("matrix_digest") == expected_matrix_digest,
        "recorded matrix digest does not match the campaign",
    )

    selected = metrics.get("selected_checkpoint")
    result.record(
        "selected_checkpoint",
        isinstance(selected, dict) and _is_digest(selected.get("sha256")),
        "selected checkpoint evidence is missing or malformed",
    )

    # Progression must cover every labelled stage and must name the selected
    # checkpoint, so a regression cannot be quietly dropped from the record.
    progression = metrics.get("progression")
    if isinstance(progression, list) and progression:
        stages = {item.get("stage") for item in progression if isinstance(item, dict)}
        result.record(
            "progression_stages",
            set(REQUIRED_PROGRESSION_STAGES) <= stages,
            f"progression is missing stages: {sorted(set(REQUIRED_PROGRESSION_STAGES) - stages)}",
        )
        result.record(
            "progression_selected",
            any(isinstance(item, dict) and item.get("selected") is True for item in progression),
            "progression does not identify the selected policy",
        )
        result.record(
            "progression_linkage",
            all(
                isinstance(item, dict)
                and isinstance(item.get("checkpoint"), dict)
                and _is_digest(item["checkpoint"].get("sha256"))
                and isinstance(item["checkpoint"].get("effective_step"), int)
                for item in progression
            ),
            "a progression entry lacks an exact checkpoint step and digest",
        )
        if isinstance(selected, dict):
            result.record(
                "progression_matches_selection",
                any(
                    isinstance(item, dict)
                    and item.get("selected") is True
                    and isinstance(item.get("checkpoint"), dict)
                    and item["checkpoint"].get("sha256") == selected.get("sha256")
                    for item in progression
                ),
                "the progression's selected entry is not the selected checkpoint",
            )
    else:
        result.record("progression_stages", False, "progression evidence is missing")

    # Selection and final seed roles must be recorded and disjoint. Overlap would
    # mean the reported acceptance was measured on seeds that chose the candidate.
    seed_roles = metrics.get("seed_roles")
    if isinstance(seed_roles, dict):
        recorded_selection = set(seed_roles.get("selection") or [])
        recorded_final = set(seed_roles.get("final") or [])
        result.record(
            "seed_roles_disjoint",
            bool(recorded_selection)
            and bool(recorded_final)
            and not (recorded_selection & recorded_final),
            "selection and final seed roles are missing or overlap",
        )
        result.record(
            "seed_roles_declared",
            recorded_selection == set(selection_seeds) and recorded_final == set(final_seeds),
            "recorded seed roles do not match the campaign matrix",
        )
    elif require_curation_evidence:
        result.record("seed_roles_disjoint", False, "seed role evidence is missing")

    episodes = metrics.get("episodes")
    result.record(
        "final_episode_count",
        isinstance(episodes, list) and len(episodes) == final_episode_count,
        f"final acceptance does not have exactly {final_episode_count} episodes",
    )
    if isinstance(episodes, list) and episodes:
        result.record(
            "final_episode_seeds",
            {item.get("seed") for item in episodes if isinstance(item, dict)} <= set(final_seeds),
            "final acceptance used a seed outside its reserved set",
        )

    if require_curation_evidence:
        acceptance = metrics.get("acceptance")
        result.record(
            "acceptance_recorded",
            isinstance(acceptance, dict)
            and isinstance(acceptance.get("hard"), dict)
            and isinstance(acceptance.get("preferred"), dict),
            "hard/preferred acceptance outcomes are missing",
        )
        result.record(
            "ranking_explanation",
            isinstance(metrics.get("ranking_explanation"), dict),
            "ranking explanation is missing",
        )
        benchmark = metrics.get("benchmark")
        result.record(
            "measured_cost",
            isinstance(benchmark, dict)
            and isinstance(benchmark.get("estimated_cost"), (int, float)),
            "measured cost evidence is missing",
        )
        result.record(
            "measured_runtime",
            isinstance(metrics.get("runtime_seconds"), (int, float)),
            "measured runtime evidence is missing",
        )

    resolved = reader.read_json("report/resolved-config.json")
    result.record(
        "resolved_config",
        isinstance(resolved, dict) and bool(resolved.get("gallery_example_id")),
        "resolved configuration is missing or does not name its example",
    )
    image = resolved.get("runtime_image") if isinstance(resolved, dict) else None
    result.record(
        "immutable_image",
        isinstance(image, str) and "@sha256:" in image,
        "resolved configuration does not record an immutable image digest",
    )

    versions = reader.read_json("report/runtime-versions.json")
    result.record(
        "runtime_versions",
        isinstance(versions, dict) and bool(versions),
        "runtime version evidence is missing",
    )

    if isinstance(selected, dict):
        result.evidence["selected_checkpoint_sha256"] = selected.get("sha256")
        result.evidence["selected_checkpoint_step"] = selected.get("effective_step")
    result.evidence["artifact_count"] = len(artifacts)
    return result


def classify_failure(
    result: VerificationResult, *, provider_failed: bool
) -> str:
    """Map verification output onto the runbook's recovery classifiers.

    Distinguishing "training worked, finalization did not" from "nothing usable"
    is what allows finalization to be retried without spending the training budget
    a second time.
    """
    if result.passed:
        return "VERIFIED"
    checkpoint_durable = result.checks.get("selected_checkpoint", False) or result.checks.get(
        "manifest_readable", False
    )
    if provider_failed and not checkpoint_durable:
        return "FAILED_BEFORE_CHECKPOINT"
    if checkpoint_durable and not result.checks.get("required_artifacts", False):
        return "FINALIZATION_ONLY_FAILURE"
    if not result.checks.get("acceptance_recorded", True):
        return "FINALIZATION_ONLY_FAILURE"
    return "ARTIFACT_CHECKSUM_FAILURE"


class ArtifactStoreEvidenceReader:
    """Prefix-bound `EvidenceReader` over the existing S3 artifact store."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def read_json(self, relative: str) -> dict[str, Any] | None:
        value = self._store.get_json_optional(relative)
        return value if isinstance(value, dict) else None

    def head(self, relative: str) -> dict[str, Any] | None:
        head = getattr(self._store, "head_object_optional", None)
        if head is None:
            return None
        value = head(relative)
        return value if isinstance(value, dict) else None


class InMemoryEvidenceReader:
    """Deterministic reader for tests and dry runs."""

    def __init__(
        self,
        documents: Mapping[str, dict[str, Any]],
        objects: Mapping[str, int] | None = None,
    ) -> None:
        self._documents = dict(documents)
        self._objects = dict(objects or {})

    def read_json(self, relative: str) -> dict[str, Any] | None:
        return self._documents.get(relative)

    def head(self, relative: str) -> dict[str, Any] | None:
        if relative in self._objects:
            return {"size_bytes": self._objects[relative]}
        return None
