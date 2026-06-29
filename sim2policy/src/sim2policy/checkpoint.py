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


def progression_checkpoints(directory: Path, total_steps: int) -> tuple[Path, Path, Path]:
    checkpoints = list_step_checkpoints(directory)
    if not checkpoints:
        raise CheckpointError(f"no completed checkpoints in {directory}")
    initial = min(checkpoints, key=lambda item: item[0])
    final = max(checkpoints, key=lambda item: item[0])
    quarter = min(checkpoints, key=lambda item: (abs(item[0] - total_steps * 0.25), item[0]))
    return initial[1], quarter[1], final[1]
