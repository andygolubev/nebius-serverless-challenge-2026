from __future__ import annotations

import argparse
import contextlib
import functools
import importlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
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
from sim2policy.runstate import STATUS_FAILED, STATUS_TRAINING, RunStateStore
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


def _environment_overrides(config: RunConfig) -> dict[str, Any]:
    return {"impl": str(config.training.hyperparameters.get("impl", "jax"))}


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
    env_overrides = _environment_overrides(config)
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
    hyperparameters["num_evals"] = max(
        2, math.ceil(config.training.total_steps / config.checkpoint.every_steps) + 1
    )
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


def _safe_extract_checkpoint(checkpoint: Path, destination: Path) -> None:
    with zipfile.ZipFile(checkpoint) as archive:
        root = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(root):
                raise RuntimeError(f"unsafe path in MJX checkpoint: {member.filename}")
        archive.extractall(destination)


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
    _safe_extract_checkpoint(checkpoint, destination)
    return destination


@contextlib.contextmanager
def mjx_policy_session(checkpoint: Path, config: RunConfig) -> Any:
    """Load a zipped Brax PPO policy and its matching Playground environment."""
    require_mjx()
    validate_checkpoint(checkpoint, config)
    with tempfile.TemporaryDirectory(prefix="sim2policy-mjx-") as temporary:
        raw_checkpoint = Path(temporary) / checkpoint.stem
        raw_checkpoint.mkdir()
        _safe_extract_checkpoint(checkpoint, raw_checkpoint)
        try:
            load_policy = importlib.import_module("brax.training.agents.ppo.checkpoint").load_policy
            registry = importlib.import_module("mujoco_playground").registry
            jax = importlib.import_module("jax")
            policy = load_policy(raw_checkpoint, deterministic=True)
            environment = registry.load(
                config.environment, config_overrides=_environment_overrides(config)
            )
        except Exception as exc:
            raise RuntimeError(
                "MJX checkpoint restore failed. Use the pinned MJX image and a checkpoint "
                "created by the same Brax/Playground version matrix."
            ) from exc
        yield jax, environment, jax.jit(policy)


def _create_initial_checkpoint(config: RunConfig, output_root: Path) -> Path:
    """Create the step-zero Brax policy checkpoint used for progression media."""
    require_mjx()
    jax = importlib.import_module("jax")
    registry = importlib.import_module("mujoco_playground").registry
    wrapper = importlib.import_module("mujoco_playground").wrapper
    playground_train = importlib.import_module("learning.train_jax_ppo")
    ppo = importlib.import_module("brax.training.agents.ppo.train")
    ppo_networks = importlib.import_module("brax.training.agents.ppo.networks")
    ppo_checkpoint = importlib.import_module("brax.training.agents.ppo.checkpoint")

    environment = registry.load(config.environment, config_overrides=_environment_overrides(config))
    ppo_params = playground_train.get_rl_config(config.environment)
    hyperparameters = dict(config.training.hyperparameters)
    hyperparameters.pop("impl", None)
    for key, value in hyperparameters.items():
        if key in {"policy_hidden_layer_sizes", "value_hidden_layer_sizes"}:
            setattr(ppo_params.network_factory, key, value)
        elif key != "network_factory":
            setattr(ppo_params, key, value)
    ppo_params.num_timesteps = 0
    # Policy initialization is independent of rollout parallelism. One environment keeps the
    # step-zero snapshot cheap while preserving the exact observation/action/network contract.
    ppo_params.num_envs = 1
    network_factory = functools.partial(
        ppo_networks.make_ppo_networks, **ppo_params.network_factory
    )
    training_params = dict(ppo_params)
    training_params.pop("network_factory", None)
    num_eval_envs = training_params.pop("num_eval_envs", 1)
    make_policy, params, _ = ppo.train(
        environment=environment,
        network_factory=network_factory,
        seed=config.seed,
        wrap_env_fn=wrapper.wrap_for_brax_training,
        num_eval_envs=num_eval_envs,
        **training_params,
    )
    del make_policy
    network_config = ppo_checkpoint.network_config(
        observation_size=environment.observation_size,
        action_size=environment.action_size,
        normalize_observations=bool(ppo_params.normalize_observations),
        network_factory=network_factory,
    )
    ppo_checkpoint.save(output_root, 0, jax.device_get(params), network_config)
    return output_root / "000000000000"


def _create_initial_checkpoint_isolated(config: RunConfig, output_root: Path) -> Path:
    """Create the initial policy in a fresh process so its JAX GPU memory is released."""
    resolved_config = output_root.parent / "initial-policy-config.yaml"
    resolved_config.parent.mkdir(parents=True, exist_ok=True)
    resolved_config.write_text(config.to_yaml(), encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "sim2policy.train_mjx",
            "--initial-worker",
            "--config",
            str(resolved_config),
            "--initial-output",
            str(output_root),
        ],
        check=True,
        text=True,
    )
    checkpoint = output_root / "000000000000"
    if not checkpoint.is_dir():
        raise RuntimeError("MJX initial policy worker produced no step-zero checkpoint")
    return checkpoint


def train_mjx(
    config: RunConfig,
    run_id: str,
    runs_root: Path,
    resume: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    initial_checkpoint_factory: Callable[[RunConfig, Path], Path] | None = None,
    state: RunStateStore | None = None,
) -> Path:
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    start_gpu = gpu_snapshot()
    environment_probe = validate_mjx_environment(config)
    paths = create_run_paths(run_id, runs_root)
    store = ArtifactStore(config.storage, run_id)
    if state is not None:
        state.update_status(
            STATUS_TRAINING,
            progress={"backend": config.backend, "environment": config.environment},
        )
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
    initial_raw_root = paths.root / "mjx_initial"
    initial_raw = (initial_checkpoint_factory or _create_initial_checkpoint_isolated)(
        config, initial_raw_root
    )
    initial = checkpoint_path(paths.checkpoints, "initial", 0)
    _archive_checkpoint(initial_raw, initial)
    write_checkpoint_metadata(initial, config, 0)
    if store.enabled:
        store.publish_checkpoint(initial, paths.root)
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
    if state is not None:
        manifest = state.discover_artifacts()
        if manifest:
            state.write_manifest(manifest)
        state.update_status(
            STATUS_TRAINING, progress={"latest_checkpoint": final.name, "trained_steps": final_step}
        )
    return final


def evaluate_mjx(checkpoint: Path, config: RunConfig) -> tuple[list[dict[str, Any]], float]:
    episodes: list[dict[str, Any]] = []
    started = time.monotonic()
    episode_length = int(config.training.hyperparameters.get("episode_length", 1000))
    seeds = [
        config.evaluation.seeds[index % len(config.evaluation.seeds)]
        for index in range(config.evaluation.episodes)
    ]
    with mjx_policy_session(checkpoint, config) as (jax, environment, policy):
        reset = jax.jit(environment.reset)
        step = jax.jit(environment.step)
        for index, seed in enumerate(seeds):
            key = jax.random.PRNGKey(seed)
            state = reset(key)
            reward_sum = 0.0
            velocities: list[float] = []
            fell = False
            length = 0
            for episode_step in range(1, episode_length + 1):
                length = episode_step
                key, action_key = jax.random.split(key)
                action, _ = policy(state.obs, action_key)
                state = step(state, action)
                reward_sum += float(state.reward)
                velocities.append(float(state.data.qvel[0]))
                if bool(state.done):
                    fell = True
                    break
            mean_velocity = sum(velocities) / len(velocities)
            success = mean_velocity >= float(config.success.min_velocity or 0)
            if config.success.require_not_fallen:
                success = success and not fell
            episodes.append(
                {
                    "index": index,
                    "seed": seed,
                    "reward": reward_sum,
                    "length": length,
                    "mean_velocity": mean_velocity,
                    "fell": fell,
                    "success": success,
                }
            )
    return episodes, time.monotonic() - started


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
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if "--initial-worker" in raw_args:
        worker = argparse.ArgumentParser()
        worker.add_argument("--initial-worker", action="store_true")
        worker.add_argument("--config", required=True)
        worker.add_argument("--initial-output", required=True, type=Path)
        worker_args = worker.parse_args(raw_args)
        _create_initial_checkpoint(load_config(worker_args.config), worker_args.initial_output)
        return
    args = build_parser().parse_args(raw_args)
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
    state = RunStateStore(config.storage, args.run_id, args.runs_root)
    try:
        final = train_mjx(config, args.run_id, args.runs_root, resume=resume, state=state)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        state.update_status(STATUS_FAILED, error=str(exc))
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps({"status": "complete", "checkpoint": str(final)}))


if __name__ == "__main__":
    main()
