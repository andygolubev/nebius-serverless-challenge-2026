from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sim2policy.config import RunConfig, redact_mapping, validate_run_id

ARTIFACT_DIRS = ("checkpoints", "tensorboard", "videos", "report")


@dataclass(frozen=True)
class RunPaths:
    root: Path
    checkpoints: Path
    tensorboard: Path
    videos: Path
    report: Path


def create_run_paths(run_id: str, runs_root: str | Path = "runs") -> RunPaths:
    validate_run_id(run_id)
    root = Path(runs_root).resolve() / run_id
    root.mkdir(parents=True, exist_ok=True)
    directories = {name: root / name for name in ARTIFACT_DIRS}
    for directory in directories.values():
        directory.mkdir(exist_ok=True)
    return RunPaths(root=root, **directories)


def _source_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def package_versions(
    names: tuple[str, ...] = (
        "sim2policy",
        "gymnasium",
        "stable-baselines3",
        "torch",
        "jax",
        "mujoco",
    ),
) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def write_metadata(
    paths: RunPaths,
    run_id: str,
    config: RunConfig,
    device: dict[str, Any] | None = None,
) -> Path:
    metadata = redact_mapping(
        {
            "schema_version": 1,
            "run_id": validate_run_id(run_id),
            "backend": config.backend,
            "environment": config.environment,
            "seed": config.seed,
            "resolved_config": config.to_dict(),
            "versions": package_versions(),
            "source_revision": _source_revision(),
            "device": device or {"platform": platform.platform()},
            "started_at": datetime.now(UTC).isoformat(),
        }
    )
    output = paths.root / "metadata.json"
    output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def storage_settings_from_env() -> dict[str, str | None]:
    return {
        "bucket": os.getenv("SIM2POLICY_S3_BUCKET"),
        "prefix": os.getenv("SIM2POLICY_S3_PREFIX"),
        "endpoint_url": os.getenv("SIM2POLICY_S3_ENDPOINT"),
        "region": os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
    }
