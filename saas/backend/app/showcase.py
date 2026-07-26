"""Public read-only showcase of curated training runs.

Everything here is reachable without a session, so it follows a stricter rule than
the tenant paths: the only input is a gallery example ID, the only storage identity
is a literal from `catalog.SHOWCASE_RUNS`, and no response field is derived from
anything a caller supplied. There is deliberately no function here that creates,
mutates, or launches anything.

Publication is gated on evidence. An entry appears only when its pinned run's
manifest reads and validates, its required artifacts are present, and its declared
identity agrees with what the run recorded. Anything else leaves the entry absent —
a normal state, not an error, because the curated runs are performed separately.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from . import catalog
from .models import Artifact, ArtifactManifest

log = logging.getLogger(__name__)

# Artifacts an anonymous visitor may reach, by logical manifest name. Explicit
# rather than derived, so an artifact the training runtime adds later is private
# by default and becomes public only by a reviewed edit here.
PUBLIC_ARTIFACT_IDS = frozenset(
    {
        # media
        "video_final",
        "video_selected",
        "video_final_step",
        "video_mid",
        "video_untrained",
        "progression_montage",
        "demo_recording",
        "reward_curve",
        # metrics and reports
        "metrics_json",
        "report_md",
        "backend_comparison",
        # provenance
        "resolved_config",
        "runtime_versions",
        # checkpoint and bundle
        "final_policy",
        "policy_bundle",
    }
)

# The required set a curated run must publish before its entry is shown. Mirrors the
# gallery contract the artifact reader already enforces; restated here so the gate is
# readable in one place.
REQUIRED_ARTIFACT_IDS = frozenset(
    {
        "final_policy",
        "metrics_json",
        "report_md",
        "video_final",
        "resolved_config",
        "runtime_versions",
        "policy_bundle",
        "video_selected",
        "video_final_step",
    }
)

# These are runtime identities, never friendly card labels.  A public run may
# not choose an environment string: it must exactly match this server-owned map.
CANONICAL_ENVIRONMENTS = {
    "reacher-target": "Reacher-v5",
    "halfcheetah-sprint": "HalfCheetah-v5",
    "ant-explorer": "Ant-v5",
    "hopper-balance": "Hopper-v5",
    "walker2d-stride": "Walker2d-v5",
    "go1-walker": "Go1JoystickFlatTerrain",
    "g1-rough-terrain": "G1JoystickRoughTerrain",
}
_UNSAFE_EVIDENCE_KEYS = frozenset(
    {"run_id", "job_id", "tenant_id", "email", "bucket", "key", "endpoint_url", "secret", "token"}
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# How long a failed or absent pinned run is remembered as unpublished. Keeps a
# permanently-missing run (the normal state until the curated runs land) from
# re-hitting object storage on every anonymous request.
NEGATIVE_TTL_SECONDS = 120.0

# Public request budget per client. Generous enough for a visitor loading the
# showcase and scrubbing a video, tight enough to bound anonymous abuse.
PUBLIC_RATE_LIMIT = 240
PUBLIC_RATE_WINDOW_SECONDS = 60.0
# Bounds the limiter's own memory: an attacker rotating source addresses must not
# grow this dictionary without limit.
_MAX_TRACKED_CLIENTS = 8192


class RateLimiter:
    """Per-client sliding window, the same shape as the auth code-request limiter.

    Keyed by client address rather than identity, because the showcase has no
    identity. One client exceeding its budget never affects another.
    """

    def __init__(
        self,
        limit: int = PUBLIC_RATE_LIMIT,
        window_seconds: float = PUBLIC_RATE_WINDOW_SECONDS,
        *,
        clock=time.time,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._seen: dict[str, list[float]] = {}

    def allow(self, client: str) -> bool:
        now = self._clock()
        with self._lock:
            if len(self._seen) > _MAX_TRACKED_CLIENTS:
                self._seen = {
                    key: [t for t in stamps if now - t < self._window]
                    for key, stamps in self._seen.items()
                }
                self._seen = {k: v for k, v in self._seen.items() if v}
            times = [t for t in self._seen.get(client, []) if now - t < self._window]
            if len(times) >= self._limit:
                self._seen[client] = times
                return False
            times.append(now)
            self._seen[client] = times
            return True


class ShowcaseService:
    """Resolves published showcase entries from pinned curated runs.

    `reader` is resolved lazily from the orchestration backend so a deployment
    without artifact storage (the mock backend) simply publishes nothing.
    """

    def __init__(
        self,
        store: Any,
        backend: Any,
        settings: Any,
        *,
        clock=time.monotonic,
    ) -> None:
        self._store = store
        self._backend = backend
        self._settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        self._unpublished_until: dict[str, float] = {}

    # -- evidence gate --

    @property
    def enabled(self) -> bool:
        return bool(self._settings.enabled)

    @property
    def _reader(self) -> Any | None:
        return getattr(self._backend, "artifact_reader", None)

    def _mark_unpublished(self, example_id: str, reason: str) -> None:
        with self._lock:
            self._unpublished_until[example_id] = self._clock() + NEGATIVE_TTL_SECONDS
        log.info("showcase entry %s is unpublished: %s", example_id, reason)

    def _recently_unpublished(self, example_id: str) -> bool:
        with self._lock:
            until = self._unpublished_until.get(example_id)
            if until is None:
                return False
            if until <= self._clock():
                del self._unpublished_until[example_id]
                return False
            return True

    def _manifest(self, example_id: str) -> ArtifactManifest | None:
        """Return the validated manifest for a published entry, else None.

        Reads are served from the durable artifact cache keyed by the pinned run
        identity, so anonymous traffic does not crawl storage per request.
        """
        if not self._settings.enabled:
            return None
        run_id = catalog.resolve_showcase_run(example_id)
        if run_id is None:
            return None
        cached = self._store.get_artifacts(run_id)
        if cached is not None:
            return cached if self._is_complete(example_id, cached) else None
        if self._recently_unpublished(example_id):
            return None
        reader = self._reader
        if reader is None:
            self._mark_unpublished(example_id, "no artifact storage is configured")
            return None
        try:
            manifest = reader.read_showcase_manifest(run_id)
        except Exception as exc:
            # Sanitized: the storage error never reaches a caller or the log message.
            self._mark_unpublished(
                example_id, f"manifest validation failed ({type(exc).__name__})"
            )
            return None
        if manifest is None:
            self._mark_unpublished(example_id, "curated run has published no manifest")
            return None
        if not self._is_complete(example_id, manifest):
            return None
        self._store.set_artifacts(manifest)
        return manifest

    def _is_complete(self, example_id: str, manifest: ArtifactManifest) -> bool:
        """Check the run recorded everything the entry claims, and agrees with it."""
        example = catalog.GALLERY_EXAMPLES.get(example_id)
        if example is None:
            return False
        present = {item.id for item in manifest.artifacts}
        missing = REQUIRED_ARTIFACT_IDS - present
        if missing:
            self._mark_unpublished(
                example_id, f"required artifacts are absent: {sorted(missing)}"
            )
            return False
        for item in manifest.artifacts:
            if item.id in PUBLIC_ARTIFACT_IDS and not (item.id and item.name and item.content_type):
                self._mark_unpublished(example_id, "artifact metadata is incomplete")
                return False
        if not isinstance(manifest.metrics, dict) or not manifest.metrics:
            self._mark_unpublished(example_id, "curated run recorded no metrics")
            return False
        # Declared identity must match what the run actually recorded, so a stale
        # card cannot advertise a configuration its pinned run did not execute.
        recorded_env = manifest.metrics.get("environment")
        if recorded_env != CANONICAL_ENVIRONMENTS[example_id]:
            self._mark_unpublished(
                example_id, "declared environment disagrees with the recorded run"
            )
            return False
        recorded_backend = manifest.metrics.get("backend")
        expected_backend = "mjx" if example.algorithm == "ppo-mjx" else "sb3"
        if isinstance(recorded_backend, str) and recorded_backend != expected_backend:
            self._mark_unpublished(
                example_id, "declared backend disagrees with the recorded run"
            )
            return False
        evaluation = self._normalized_success(manifest.metrics)
        if evaluation is None or not evaluation["success"]:
            self._mark_unpublished(example_id, "curated run did not record a passing success.met")
            return False
        selected = manifest.metrics.get("selected_checkpoint")
        progression = manifest.metrics.get("progression")
        if not isinstance(selected, dict) or not isinstance(selected.get("sha256"), str):
            self._mark_unpublished(example_id, "selected checkpoint evidence is missing")
            return False
        if not isinstance(progression, list) or not progression:
            self._mark_unpublished(example_id, "progression evidence is missing")
            return False
        if not any(isinstance(item, dict) and item.get("selected") is True for item in progression):
            self._mark_unpublished(example_id, "progression does not identify selected policy")
            return False
        if not _SHA256.fullmatch(str(selected.get("sha256", ""))):
            self._mark_unpublished(example_id, "selected checkpoint digest is invalid")
            return False
        if not _SHA256.fullmatch(str(manifest.metrics.get("matrix_digest", ""))):
            self._mark_unpublished(example_id, "matrix digest is missing or invalid")
            return False
        resolved = manifest.metrics.get("resolved_config")
        image = resolved.get("runtime_image") if isinstance(resolved, dict) else None
        if not isinstance(image, str) or "@sha256:" not in image:
            self._mark_unpublished(example_id, "runtime image is not an immutable digest")
            return False
        benchmark = manifest.metrics.get("benchmark")
        if not isinstance(benchmark, dict) or not isinstance(benchmark.get("estimated_cost"), int | float):
            self._mark_unpublished(example_id, "measured cost evidence is missing")
            return False
        return True

    # -- serialization --

    def _display(self, example_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
        """Display metadata for an entry.

        Contains no tenant identity, job ID, bucket name, object key, credential, or
        presigned URL — only the server-owned description of what ran.
        """
        example = catalog.GALLERY_EXAMPLES[example_id]
        benchmark = metrics.get("benchmark") if isinstance(metrics.get("benchmark"), dict) else {}
        selected = metrics.get("selected_checkpoint") if isinstance(metrics.get("selected_checkpoint"), dict) else {}
        resolved = metrics.get("resolved_config") if isinstance(metrics.get("resolved_config"), dict) else {}
        return {
            "id": example.id,
            "label": example.label,
            "task": example.task,
            "description": example.description,
            "avatar": example.avatar,
            "expected_result": example.expected_result,
            "backend_label": str(metrics.get("backend", example.backend_label)),
            "hardware_label": str(resolved.get("hardware_label", "measured Nebius run")),
            "observed_duration": metrics.get("runtime_seconds"),
            "observed_cost": benchmark.get("estimated_cost"),
            "rate_date": benchmark.get("rate_date"),
            "acceptance_revision": example.acceptance_revision,
            # What the curated run executed, for display only. No submittable
            # environment, algorithm, preset, profile, or parameter contract.
            "executed_config": {
                "environment": metrics.get("environment"),
                "algorithm_label": str(metrics.get("backend", example.backend_label)),
                "total_timesteps": resolved.get("training", {}).get("total_steps") if isinstance(resolved.get("training"), dict) else None,
                "platform": resolved.get("hardware", {}).get("platform") if isinstance(resolved.get("hardware"), dict) else None,
                "preset": resolved.get("hardware", {}).get("preset") if isinstance(resolved.get("hardware"), dict) else None,
            },
            "selected_checkpoint": {
                "step": selected.get("effective_step"),
                "sha256": selected.get("sha256"),
            },
        }

    def _public_artifacts(
        self, example_id: str, manifest: ArtifactManifest
    ) -> list[dict[str, Any]]:
        """Allowlisted artifacts with opaque route URLs.

        URLs point at this service, never at a presigned URL directly: a presign is
        short-lived and the catalog response is cached, so an embedded one would be
        served already expired. The redirect mints a fresh one per access.
        """
        items = []
        for artifact in manifest.artifacts:
            if artifact.id not in PUBLIC_ARTIFACT_IDS:
                continue
            base = f"/showcase/{example_id}/artifacts/{artifact.id}"
            items.append(
                {
                    "id": artifact.id,
                    "name": artifact.name,
                    "kind": artifact.kind,
                    "content_type": artifact.content_type,
                    "size_bytes": artifact.size_bytes,
                    "sha256": artifact.sha256,
                    "url": base,
                    "download_url": f"{base}?download=true",
                }
            )
        return items

    def _normalized_success(self, metrics: dict[str, Any]) -> dict[str, Any] | None:
        success = metrics.get("success")
        if not isinstance(success, dict) or set(success) - {"met", "criterion"}:
            return None
        if not isinstance(success.get("met"), bool) or not isinstance(success.get("criterion"), str):
            return None
        return {"success": success["met"], "criterion": success["criterion"]}

    def _evaluation(self, manifest: ArtifactManifest, example_id: str) -> dict[str, Any]:
        """Evaluation outcome, kept separate from infrastructure completion.

        A run that produced every artifact but missed its task threshold is a
        completed run with an unmet evaluation, not a failed job.
        """
        metrics = manifest.metrics if isinstance(manifest.metrics, dict) else {}
        normalized = self._normalized_success(metrics)
        if normalized is None:
            return {"success": None, "criterion": None, "primary_metric": None}
        aggregate = metrics.get("aggregate") if isinstance(metrics.get("aggregate"), dict) else {}
        return {
            "success": normalized["success"],
            "criterion": normalized["criterion"],
            "primary_metric": aggregate.get("mean_velocity", aggregate.get("mean_reward")),
        }

    def _public_metrics(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._public_metrics(item)
                for key, item in value.items()
                if str(key).lower() not in _UNSAFE_EVIDENCE_KEYS
            }
        if isinstance(value, list):
            return [self._public_metrics(item) for item in value]
        return value

    # -- public reads --

    def entries(self) -> list[dict[str, Any]]:
        """Published entries in documented gallery order; empty when none validate."""
        published = []
        for example_id in catalog.GALLERY_EXAMPLES:
            manifest = self._manifest(example_id)
            if manifest is None:
                continue
            entry = self._display(example_id, manifest.metrics)
            entry["evaluation"] = self._evaluation(manifest, example_id)
            entry["has_media"] = any(
                item.kind == "video"
                for item in manifest.artifacts
                if item.id in PUBLIC_ARTIFACT_IDS
            )
            published.append(entry)
        return published

    def detail(self, example_id: str) -> dict[str, Any] | None:
        """Full read-only result for one published entry, or None for 404.

        None covers unknown, hidden, and gate-failing entries alike so a caller
        cannot tell which case applies.
        """
        if example_id not in catalog.GALLERY_EXAMPLES:
            return None
        manifest = self._manifest(example_id)
        if manifest is None:
            return None
        detail = self._display(example_id, manifest.metrics)
        detail["evaluation"] = self._evaluation(manifest, example_id)
        # Infrastructure completion, reported separately from the evaluation above.
        detail["status"] = manifest.status
        detail["metrics"] = self._public_metrics(manifest.metrics)
        detail["progression"] = self._public_metrics(manifest.metrics.get("progression", []))
        detail["artifacts"] = self._public_artifacts(example_id, manifest)
        return detail

    def artifact(self, example_id: str, artifact_id: str) -> Artifact | None:
        """Resolve an allowlisted artifact of a published entry, or None for 404."""
        if artifact_id not in PUBLIC_ARTIFACT_IDS:
            return None
        if example_id not in catalog.GALLERY_EXAMPLES:
            return None
        manifest = self._manifest(example_id)
        if manifest is None:
            return None
        return next(
            (item for item in manifest.artifacts if item.id == artifact_id), None
        )

    def presigned(self, artifact: Artifact, *, download: bool) -> str | None:
        """Mint a short-lived read-only URL for exactly one validated object."""
        reader = self._reader
        if reader is None or not hasattr(reader, "presigned_url"):
            return None
        filename = artifact.key.rsplit("/", 1)[-1] if download else None
        return reader.presigned_url(
            artifact.key,
            content_type=artifact.content_type,
            download_name=filename,
        )


def serialize_options(service: ShowcaseService) -> dict[str, Any]:
    """`/training-options` as showcase display metadata.

    Advertises no submittable environment, algorithm, preset, profile, or parameter
    contract, because no field of it is accepted by any job-creating endpoint.
    """
    return {"showcase_enabled": service.enabled, "examples": service.entries()}
