from __future__ import annotations

import argparse
import importlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml

from sim2policy.checkpoint import (
    checkpoint_path,
    latest_checkpoint,
    validate_checkpoint,
    write_checkpoint_metadata,
)
from sim2policy.config import RunConfig, load_config
from sim2policy.run import RunPaths, create_run_paths, write_metadata
from sim2policy.storage import ArtifactStore
from sim2policy.telemetry import gpu_snapshot, runtime_record, utc_now_iso, write_runtime_record

_MJX_MODULES = ("jax", "mujoco", "mujoco_playground", "brax")
_PLAYGROUND_FLAG_MAP = {
    "num_eval_envs",
    "num_evals",
    "batch_size",
    "num_minibatches",
    "num_updates_per_batch",
    "unroll_length",
    "episode_length",
    "learning_rate",
    "entropy_cost",
    "discounting",
    "reward_scaling",
    "action_repeat",
    "clipping_epsilon",
    "max_grad_norm",
    "training_metrics_steps",
    "policy_obs_key",
    "value_obs_key",
    "policy_hidden_layer_sizes",
    "value_hidden_layer_sizes",
}


def _json_flag(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def require_mjx() -> None:
    missing: list[str] = []
    for module in _MJX_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        raise RuntimeError(
            "MJX dependencies are unavailable: "
            + ", ".join(missing)
            + ". Install with `uv sync --extra mjx` or use the MJX container target."
        )


def validate_mjx_environment(config: RunConfig) -> dict[str, Any]:
    require_mjx()
    registry = importlib.import_module("mujoco_playground").registry
    env_overrides = {"impl": str(config.training.hyperparameters.get("impl", "jax"))}
    try:
        env = registry.load(config.environment, config_overrides=env_overrides)
    except Exception as exc:
        raise RuntimeError(
            f"MJX environment `{config.environment}` failed to load with overrides "
            f"{env_overrides}. Use an explicit supported Playground environment and `impl: jax`."
        ) from exc
    return {
        "environment": config.environment,
        "impl": env_overrides["impl"],
        "observation_size": getattr(env, "observation_size", None),
        "action_size": getattr(env, "action_size", None),
    }


def build_playground_command(
    config: RunConfig,
    paths: RunPaths,
    *,
    resume: Path | None = None,
) -> list[str]:
    hyperparameters = dict(config.training.hyperparameters)
    impl = str(hyperparameters.pop("impl", "jax"))
    command = [
        "train-jax-ppo",
        f"--env_name={config.environment}",
        f"--impl={impl}",
        f"--seed={config.seed}",
        f"--num_timesteps={config.training.total_steps}",
        f"--num_envs={config.training.n_envs}",
        f"--logdir={paths.root / 'mjx_logs'}",
        f"--suffix={paths.root.name}",
        "--nouse_wandb",
        "--use_tb",
        "--num_videos=0",
        "--playground_config_overrides",
        _json_flag({"impl": impl}),
    ]
    if resume is not None:
        command.append(f"--load_checkpoint_path={resume}")
    unknown = sorted(set(hyperparameters) - _PLAYGROUND_FLAG_MAP - {"network_factory"})
    if unknown:
        raise RuntimeError(f"unsupported MJX hyperparameter(s): {', '.join(unknown)}")
    for key, value in sorted(hyperparameters.items()):
        if key in {"policy_hidden_layer_sizes", "value_hidden_layer_sizes"}:
            command.append(f"--{key}={','.join(str(item) for item in value)}")
        else:
            command.append(f"--{key}={value}")
    return command


def _playground_checkpoints(raw_log_root: Path) -> list[tuple[int, Path]]:
    candidates: list[tuple[int, Path]] = []
    for checkpoint_dir in raw_log_root.glob("*/checkpoints/*"):
        if checkpoint_dir.is_dir() and checkpoint_dir.name.isdigit():
            candidates.append((int(checkpoint_dir.name), checkpoint_dir))
    if not candidates:
        raise RuntimeError(f"Playground training completed without a checkpoint in {raw_log_root}")
    return sorted(candidates, key=lambda item: item[0])


def _archive_checkpoint(raw_checkpoint: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = shutil.make_archive(str(output.with_suffix("")), "zip", raw_checkpoint)
    archived = Path(temporary)
    if archived != output:
        archived.replace(output)
    return output


def _prepare_resume_checkpoint(checkpoint: Path, config: RunConfig, paths: RunPaths) -> Path:
    if checkpoint.is_dir():
        return checkpoint
    validate_checkpoint(checkpoint, config)
    if checkpoint.suffix != ".zip":
        raise RuntimeError(
            "MJX resume requires a raw Playground checkpoint directory or a zipped Orbax checkpoint"
        )
    destination = paths.root / "resume" / checkpoint.stem
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(checkpoint) as archive:
        archive.extractall(destination)
    return destination


def train_mjx(
    config: RunConfig,
    run_id: str,
    runs_root: Path,
    resume: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    start_gpu = gpu_snapshot()
    environment_probe = validate_mjx_environment(config)
    paths = create_run_paths(run_id, runs_root)
    store = ArtifactStore(config.storage, run_id)
    write_metadata(
        paths,
        run_id,
        config,
        {
            "requested": config.training.device,
            "mjx_environment": environment_probe,
        },
    )
    raw_resume = _prepare_resume_checkpoint(resume, config, paths) if resume is not None else None
    command = build_playground_command(config, paths, resume=raw_resume)
    runner(command, check=True, text=True)
    raw_checkpoints = _playground_checkpoints(paths.root / "mjx_logs")
    archived_checkpoints: list[Path] = []
    final_step = raw_checkpoints[-1][0]
    for step, raw_checkpoint in raw_checkpoints:
        kind = "final" if step == final_step else "step"
        checkpoint = checkpoint_path(paths.checkpoints, kind, step)
        _archive_checkpoint(raw_checkpoint, checkpoint)
        write_checkpoint_metadata(checkpoint, config, step)
        archived_checkpoints.append(checkpoint)
        if store.enabled:
            store.publish_checkpoint(checkpoint, paths.root)
    final = archived_checkpoints[-1]
    completed_at = utc_now_iso()
    write_runtime_record(
        paths.report / "runtime.json",
        runtime_record(
            started_at=started_at,
            completed_at=completed_at,
            runtime_seconds=time.monotonic() - started_monotonic,
            start_gpu=start_gpu,
            end_gpu=gpu_snapshot(),
        ),
    )
    store.sync_tree(paths.root, required=store.enabled)
    return final


def evaluate_mjx(checkpoint: Path, config: RunConfig) -> tuple[list[dict[str, Any]], float]:
    require_mjx()
    raise RuntimeError(
        "MJX deterministic evaluation is intentionally gated until the pinned Playground "
        "checkpoint restore API is validated on the target Linux/GPU image."
    )


def _override(value: str) -> tuple[str, Any]:
    key, separator, raw = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("override must be KEY=YAML_VALUE")
    return key, yaml.safe_load(raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train an MJX/Playground PPO locomotion policy")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--resume", nargs="?", const="latest")
    parser.add_argument("--set", action="append", default=[], type=_override, dest="overrides")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(args.config, dict(args.overrides))
    if config.backend != "mjx":
        raise SystemExit("selected config is not an MJX config")
    resume = None
    if args.resume:
        if args.resume == "remote":
            paths = create_run_paths(args.run_id, args.runs_root)
            resume = ArtifactStore(config.storage, args.run_id).resume_latest(
                paths.checkpoints, config
            )
        else:
            resume = (
                latest_checkpoint(args.runs_root / args.run_id / "checkpoints")
                if args.resume == "latest"
                else Path(args.resume)
            )
    try:
        final = train_mjx(config, args.run_id, args.runs_root, resume=resume)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps({"status": "complete", "checkpoint": str(final)}))


if __name__ == "__main__":
    main()
