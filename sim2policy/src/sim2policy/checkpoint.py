from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sim2policy.config import RunConfig

STEP_PATTERN = re.compile(r"^(?:initial|final|interrupted|step)-(\d{12})\.zip$")


class CheckpointError(ValueError):
    """Raised when a checkpoint is absent or incompatible."""


@dataclass(frozen=True)
class CheckpointMetadata:
    schema_version: int
    backend: str
    environment: str
    step: int
    seed: int
    checkpoint: str
    sha256: str


@dataclass(frozen=True)
class CheckpointInventory:
    """One immutable checkpoint record used by selection and finalization."""

    backend: str
    run_lineage: str
    effective_step: int
    native_path: str
    sha256: str
    phase: str
    environment: str
    load_compatible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_path(directory: Path, kind: str, step: int, suffix: str = ".zip") -> Path:
    if kind not in {"initial", "step", "final", "interrupted"}:
        raise CheckpointError(f"unsupported checkpoint kind: {kind}")
    return directory / f"{kind}-{step:012d}{suffix}"


def metadata_path(checkpoint: Path) -> Path:
    return checkpoint.with_suffix(checkpoint.suffix + ".json")


def write_checkpoint_metadata(checkpoint: Path, config: RunConfig, step: int) -> Path:
    metadata = CheckpointMetadata(
        schema_version=1,
        backend=config.backend,
        environment=config.environment,
        step=step,
        seed=config.seed,
        checkpoint=checkpoint.name,
        sha256=sha256_file(checkpoint),
    )
    output = metadata_path(checkpoint)
    output.write_text(json.dumps(asdict(metadata), indent=2, sort_keys=True) + "\n")
    return output


def load_checkpoint_metadata(checkpoint: Path) -> CheckpointMetadata:
    sidecar = metadata_path(checkpoint)
    if not checkpoint.is_file() or not sidecar.is_file():
        raise CheckpointError(f"checkpoint or metadata missing: {checkpoint}")
    raw: dict[str, Any] = json.loads(sidecar.read_text())
    metadata = CheckpointMetadata(**raw)
    if metadata.checkpoint != checkpoint.name:
        raise CheckpointError("checkpoint metadata filename mismatch")
    if metadata.sha256 != sha256_file(checkpoint):
        raise CheckpointError("checkpoint checksum mismatch")
    return metadata


def validate_checkpoint(checkpoint: Path, config: RunConfig) -> CheckpointMetadata:
    metadata = load_checkpoint_metadata(checkpoint)
    if metadata.backend != config.backend or metadata.environment != config.environment:
        raise CheckpointError(
            f"checkpoint is for {metadata.backend}/{metadata.environment}, "
            f"not {config.backend}/{config.environment}"
        )
    return metadata


def list_step_checkpoints(directory: Path) -> list[tuple[int, Path]]:
    checkpoints: list[tuple[int, Path]] = []
    for path in directory.glob("*.zip"):
        match = STEP_PATTERN.match(path.name)
        if match and metadata_path(path).is_file():
            checkpoints.append((int(match.group(1)), path))
    return sorted(checkpoints)


def latest_checkpoint(directory: Path) -> Path:
    checkpoints = list_step_checkpoints(directory)
    if not checkpoints:
        raise CheckpointError(f"no completed checkpoints in {directory}")
    return checkpoints[-1][1]


def nearest_checkpoint(directory: Path, target_step: int) -> Path:
    """Return the retained checkpoint closest to `target_step`.

    Used for milestone gates (e.g. the G1 flat gate schedule) where training
    cadence may not land on the exact nominal step.
    """
    checkpoints = list_step_checkpoints(directory)
    if not checkpoints:
        raise CheckpointError(f"no completed checkpoints in {directory}")
    return min(checkpoints, key=lambda item: (abs(item[0] - target_step), item[0]))[1]


def progression_checkpoints(directory: Path, total_steps: int) -> tuple[Path, Path, Path]:
    checkpoints = list_step_checkpoints(directory)
    if not checkpoints:
        raise CheckpointError(f"no completed checkpoints in {directory}")
    initial = min(checkpoints, key=lambda item: item[0])
    final = max(checkpoints, key=lambda item: item[0])
    quarter = min(checkpoints, key=lambda item: (abs(item[0] - total_steps * 0.25), item[0]))
    return initial[1], quarter[1], final[1]


def checkpoint_inventory(
    checkpoint: Path,
    config: RunConfig,
    *,
    run_lineage: str,
    phase: str = "training",
) -> CheckpointInventory:
    """Load and attest a checkpoint before it can enter curated evidence."""
    metadata = validate_checkpoint(checkpoint, config)
    return CheckpointInventory(
        backend=metadata.backend,
        run_lineage=run_lineage,
        effective_step=metadata.step,
        native_path=checkpoint.name,
        sha256=metadata.sha256,
        phase=phase,
        environment=metadata.environment,
        load_compatible=True,
    )


def checkpoint_by_digest(directory: Path, digest: str) -> Path:
    """Resolve exactly one local checkpoint by verified digest, never by a UI label."""
    matches = [
        path
        for _, path in list_step_checkpoints(directory)
        if load_checkpoint_metadata(path).sha256 == digest
    ]
    if len(matches) != 1:
        raise CheckpointError("selected checkpoint digest does not resolve uniquely")
    return matches[0]
