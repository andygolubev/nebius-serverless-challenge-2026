"""Per-run state and artifact persistence shared by the API, orchestration
backends, and training entrypoints.

The object-storage layout under a run prefix (`<prefix>/<run_id>/`) is fixed:

    metadata/status.json     run-status lifecycle + progress summary
    metadata/request.json    the validated demo request that started the run
    checkpoints/             policy checkpoints (written by training)
    tensorboard/             TensorBoard event files (written by training)
    videos/{untrained,mid,final,progression_montage}.mp4
    report/metrics.json
    report/report.md
    report/artifacts.json    manifest mapping logical artifact names -> object keys

State files are written directly (not only at final sync) so the API can read a
run's status and artifacts mid-run, whether the run executes on S3-backed
storage or purely locally (mock backend / local template mode).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from sim2policy.checkpoint import sha256_file
from sim2policy.config import StorageConfig, validate_run_id
from sim2policy.storage import ArtifactStore

# Run status lifecycle. Terminal states are `completed` and `failed`.
STATUS_QUEUED = "queued"
STATUS_STARTING = "starting"
STATUS_TRAINING = "training"
STATUS_RENDERING = "rendering"
STATUS_EVALUATING = "evaluating"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

LIFECYCLE: tuple[str, ...] = (
    STATUS_QUEUED,
    STATUS_STARTING,
    STATUS_TRAINING,
    STATUS_RENDERING,
    STATUS_EVALUATING,
    STATUS_COMPLETED,
)
TERMINAL_STATES = frozenset({STATUS_COMPLETED, STATUS_FAILED})
ALL_STATES = frozenset({*LIFECYCLE, STATUS_FAILED})

# Fixed relative keys within a run prefix.
STATUS_KEY = "metadata/status.json"
REQUEST_KEY = "metadata/request.json"
MANIFEST_KEY = "report/artifacts.json"

# Logical artifact names exposed by the API, mapped to their fixed object keys.
ARTIFACT_KEYS: dict[str, str] = {
    "final_policy": "checkpoints/final.zip",
    "metrics_json": "report/metrics.json",
    "report_md": "report/report.md",
    "reward_curve": "report/reward-curve.png",
    "backend_comparison": "report/backend-comparison.md",
    "video_untrained": "videos/untrained.mp4",
    "video_mid": "videos/mid.mp4",
    "video_final": "videos/final.mp4",
    "video_selected": "videos/selected.mp4",
    "video_final_step": "videos/final-step.mp4",
    "progression_montage": "videos/progression_montage.mp4",
    "demo_recording": "videos/demo-recording.mp4",
    "resolved_config": "report/resolved-config.json",
    "runtime_versions": "report/runtime-versions.json",
    "policy_bundle": "bundle/policy-bundle.zip",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    status: str
    created_at: str
    updated_at: str
    preset: str | None = None
    progress: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "run_id": self.run_id,
            "preset": self.preset,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "progress": self.progress,
        }
        if self.error is not None:
            data["error"] = self.error
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RunStatus:
        return cls(
            run_id=str(data["run_id"]),
            status=str(data["status"]),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            preset=data.get("preset"),
            progress=dict(data.get("progress") or {}),
            error=data.get("error"),
        )


class RunStateStore:
    """Reads and writes the per-run state files for a single run.

    Persists to S3-compatible storage when the run uses `s3` storage mode, and
    always mirrors to the local run tree so local/mock runs and the demo UI work
    without object storage.
    """

    def __init__(
        self,
        storage: StorageConfig,
        run_id: str,
        runs_root: str | Path = "runs",
        *,
        client: Any | None = None,
    ) -> None:
        self.run_id = validate_run_id(run_id)
        self.storage = storage
        self.runs_root = Path(runs_root)
        self.store = ArtifactStore(storage, run_id, client=client)

    @property
    def enabled(self) -> bool:
        return self.store.enabled

    @property
    def run_root(self) -> Path:
        return self.runs_root / self.run_id

    def _local_path(self, relative: str | PurePosixPath) -> Path:
        return self.run_root / Path(str(relative))

    def write_json(self, relative: str, payload: dict[str, Any]) -> None:
        local = self._local_path(relative)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if self.enabled:
            self.store.put_json(relative, payload)

    def read_json(self, relative: str) -> dict[str, Any] | None:
        if self.enabled:
            remote = self.store.get_json_optional(relative)
            if remote is not None:
                return remote
        local = self._local_path(relative)
        if local.is_file():
            result = json.loads(local.read_text(encoding="utf-8"))
            if isinstance(result, dict):
                return result
        return None

    # -- request -----------------------------------------------------------
    def write_request(self, request: dict[str, Any]) -> None:
        self.write_json(REQUEST_KEY, request)

    def read_request(self) -> dict[str, Any] | None:
        return self.read_json(REQUEST_KEY)

    # -- status ------------------------------------------------------------
    def init_status(self, *, preset: str | None, status: str = STATUS_QUEUED) -> RunStatus:
        now = utc_now_iso()
        state = RunStatus(
            run_id=self.run_id,
            status=status,
            created_at=now,
            updated_at=now,
            preset=preset,
            progress={"phase": status},
        )
        self.write_json(STATUS_KEY, state.to_dict())
        return state

    def read_status(self) -> RunStatus | None:
        data = self.read_json(STATUS_KEY)
        return RunStatus.from_dict(data) if data is not None else None

    def update_status(
        self,
        status: str,
        *,
        progress: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> RunStatus:
        if status not in ALL_STATES:
            raise ValueError(f"unknown run status: {status}")
        existing = self.read_status()
        created_at = existing.created_at if existing else utc_now_iso()
        preset = existing.preset if existing else None
        merged = dict(existing.progress) if existing else {}
        if progress:
            merged.update(progress)
        merged["phase"] = status
        state = RunStatus(
            run_id=self.run_id,
            status=status,
            created_at=created_at,
            updated_at=utc_now_iso(),
            preset=preset,
            progress=merged,
            error=error,
        )
        self.write_json(STATUS_KEY, state.to_dict())
        return state

    # -- artifacts ---------------------------------------------------------
    def write_manifest(
        self, artifacts: dict[str, str], *, evidence: Mapping[str, Any] | None = None
    ) -> None:
        checksums = {
            name: {
                "sha256": sha256_file(self._local_path(relative)),
                "size_bytes": self._local_path(relative).stat().st_size,
            }
            for name, relative in artifacts.items()
        }
        payload: dict[str, Any] = {"artifacts": artifacts, "checksums": checksums}
        if evidence:
            # Curation evidence (matrix digest, phase lineage, selected checkpoint,
            # ranking explanation, seed roles, hard/preferred outcomes, measured
            # runtime/cost) mirrored here so the checksummed manifest stays a
            # complete, self-contained curation record on its own.
            payload["curation_evidence"] = dict(evidence)
        self.write_json(MANIFEST_KEY, payload)

    def read_manifest(self) -> dict[str, str]:
        data = self.read_json(MANIFEST_KEY)
        if not data:
            return {}
        artifacts = data.get("artifacts") or {}
        return {str(name): str(key) for name, key in artifacts.items()}

    def discover_artifacts(self) -> dict[str, str]:
        """Build a manifest from artifacts that currently exist on disk.

        Used by training entrypoints and the mock backend to record only the
        artifacts that were actually produced.
        """
        found: dict[str, str] = {}
        for name, key in ARTIFACT_KEYS.items():
            if self._local_path(key).is_file():
                found[name] = key
        return found

    def artifact_url(self, key: str, *, expires: int = 3600) -> str:
        if self.enabled:
            return self.store.presigned_url(key, expires=expires)
        return str(self._local_path(key))

    def artifact_urls(self, *, expires: int = 3600) -> dict[str, str]:
        manifest = self.read_manifest()
        return {name: self.artifact_url(key, expires=expires) for name, key in manifest.items()}
