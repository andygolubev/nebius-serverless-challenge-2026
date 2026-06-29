from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sim2policy.config import RunConfig, load_config
from sim2policy.run import create_run_paths, write_metadata


def require_mjx() -> None:
    try:
        import jax  # type: ignore[import-not-found] # noqa: F401
        import mujoco_playground  # type: ignore[import-not-found] # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "MJX dependencies unavailable; use the mjx image or `uv sync --extra mjx`"
        ) from exc


def train_mjx(config: RunConfig, run_id: str, runs_root: Path) -> Path:
    require_mjx()
    paths = create_run_paths(run_id, runs_root)
    write_metadata(paths, run_id, config)
    command = [
        "train-jax-ppo",
        "--env_name",
        config.environment,
        "--seed",
        str(config.seed),
        "--num_timesteps",
        str(config.training.total_steps),
        "--checkpoint_dir",
        str(paths.checkpoints),
    ]
    subprocess.run(command, check=True)
    candidates = sorted(
        paths.checkpoints.rglob("*"), key=lambda path: path.stat().st_mtime if path.is_file() else 0
    )
    files = [path for path in candidates if path.is_file()]
    if not files:
        raise RuntimeError("Playground training completed without a checkpoint")
    return files[-1]


def evaluate_mjx(checkpoint: Path, config: RunConfig) -> tuple[list[dict[str, Any]], float]:
    require_mjx()
    raise RuntimeError("MJX checkpoint evaluation adapter requires Linux/GPU API validation")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if config.backend != "mjx":
        raise SystemExit("selected config is not an MJX config")
    print(json.dumps({"checkpoint": str(train_mjx(config, args.run_id, args.runs_root))}))


if __name__ == "__main__":
    main()
