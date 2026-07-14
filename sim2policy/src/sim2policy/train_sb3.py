from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import (
    checkpoint_path,
    latest_checkpoint,
    validate_checkpoint,
    write_checkpoint_metadata,
)
from sim2policy.config import RunConfig, load_config, parse_override
from sim2policy.run import RunPaths, create_run_paths, write_metadata
from sim2policy.runstate import STATUS_FAILED, STATUS_TRAINING, RunStateStore
from sim2policy.storage import ArtifactStore
from sim2policy.telemetry import gpu_snapshot, runtime_record, utc_now_iso, write_runtime_record


def _imports() -> tuple[Any, Any, Any, Any, Any]:
    try:
        PPO = importlib.import_module("stable_baselines3").PPO
        callbacks = importlib.import_module("stable_baselines3.common.callbacks")
        BaseCallback = callbacks.BaseCallback
        CallbackList = callbacks.CallbackList
        EvalCallback = callbacks.EvalCallback
        make_vec_env = importlib.import_module(
            "stable_baselines3.common.env_util"
        ).make_vec_env
    except ImportError as exc:
        raise RuntimeError(
            "SB3 dependencies are unavailable; install with `uv sync --extra sb3` "
            "or use the SB3 container target"
        ) from exc
    return PPO, BaseCallback, CallbackList, EvalCallback, make_vec_env


def _save_model(model: Any, path: Path, config: RunConfig) -> Path:
    model.save(path.with_suffix(""))
    if not path.is_file():
        raise RuntimeError(f"SB3 did not create expected checkpoint: {path}")
    write_checkpoint_metadata(path, config, int(model.num_timesteps))
    return path


def build_checkpoint_callback(
    config: RunConfig,
    paths: RunPaths,
    sync_hook: Callable[[Path], None] | None = None,
    eval_env: Any | None = None,
) -> Any:
    _, BaseCallback, CallbackList, EvalCallback, _ = _imports()

    class DurableCheckpointCallback(BaseCallback):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__(verbose=0)
            self.next_step = config.checkpoint.every_steps

        def _on_training_start(self) -> None:
            current = int(self.model.num_timesteps)
            self.next_step = (
                (current // config.checkpoint.every_steps) + 1
            ) * config.checkpoint.every_steps

        def _on_step(self) -> bool:
            current = int(self.model.num_timesteps)
            if current < self.next_step:
                return True
            output = checkpoint_path(paths.checkpoints, "step", current)
            _save_model(self.model, output, config)
            if sync_hook:
                sync_hook(output)
            self.next_step += config.checkpoint.every_steps
            if config.checkpoint.keep > 0:
                periodic = sorted(paths.checkpoints.glob("step-*.zip"))
                for stale in periodic[: -config.checkpoint.keep]:
                    stale.unlink(missing_ok=True)
                    stale.with_suffix(stale.suffix + ".json").unlink(missing_ok=True)
            return True

    callbacks = [DurableCheckpointCallback()]
    if eval_env is not None:
        eval_log_path = paths.report / "eval"
        best_model_path = paths.checkpoints / "best"
        eval_log_path.mkdir(parents=True, exist_ok=True)
        best_model_path.mkdir(parents=True, exist_ok=True)
        callbacks.append(
            EvalCallback(
                eval_env,
                best_model_save_path=str(best_model_path),
                log_path=str(eval_log_path),
                eval_freq=max(config.checkpoint.every_steps // config.training.n_envs, 1),
                n_eval_episodes=config.evaluation.episodes,
                deterministic=True,
                render=False,
                warn=False,
            )
        )
    return CallbackList(callbacks) if len(callbacks) > 1 else callbacks[0]


def train(
    config: RunConfig,
    run_id: str,
    runs_root: Path,
    resume: Path | None = None,
    sync_hook: Callable[[Path], None] | None = None,
    state: RunStateStore | None = None,
) -> Path:
    PPO, _, _, _, make_vec_env = _imports()
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    start_gpu = gpu_snapshot()
    paths = create_run_paths(run_id, runs_root)
    store = ArtifactStore(config.storage, run_id)
    if sync_hook is None and store.enabled:

        def publish(checkpoint: Path) -> None:
            store.publish_checkpoint(checkpoint, paths.root)
            store.sync_runtime_artifacts(paths.root)

        sync_hook = publish
    if state is not None:
        inner_hook = sync_hook

        def _state_hook(checkpoint: Path) -> None:
            if inner_hook is not None:
                inner_hook(checkpoint)
            state.update_status(
                STATUS_TRAINING, progress={"latest_checkpoint": checkpoint.name}
            )

        sync_hook = _state_hook
    write_metadata(paths, run_id, config, {"requested": config.training.device})
    if state is not None:
        state.update_status(
            STATUS_TRAINING,
            progress={"backend": config.backend, "environment": config.environment},
        )
    env = make_vec_env(
        config.environment,
        n_envs=config.training.n_envs,
        seed=config.seed,
    )
    eval_env = make_vec_env(
        config.environment,
        n_envs=1,
        seed=config.seed + 10_000,
    )
    if resume:
        resume_metadata = validate_checkpoint(resume, config)
        model = PPO.load(resume, env=env, device=config.training.device)
        if int(model.num_timesteps) != resume_metadata.step:
            raise RuntimeError("checkpoint timestep does not match its metadata")
        learn_steps = config.training.total_steps - int(model.num_timesteps)
        if learn_steps <= 0:
            raise RuntimeError("checkpoint has already reached the configured training budget")
        reset_num_timesteps = False
    else:
        model = PPO(
            "MlpPolicy",
            env,
            device=config.training.device,
            tensorboard_log=str(paths.tensorboard),
            seed=config.seed,
            verbose=1,
            **config.training.hyperparameters,
        )
        initial = checkpoint_path(paths.checkpoints, "initial", 0)
        _save_model(model, initial, config)
        learn_steps = config.training.total_steps
        reset_num_timesteps = True

    callback = build_checkpoint_callback(config, paths, sync_hook, eval_env)
    completed = False
    try:
        model.learn(
            total_timesteps=learn_steps,
            callback=callback,
            reset_num_timesteps=reset_num_timesteps,
            tb_log_name=run_id,
        )
        completed = True
    except KeyboardInterrupt:
        interrupted = checkpoint_path(paths.checkpoints, "interrupted", int(model.num_timesteps))
        _save_model(model, interrupted, config)
        if sync_hook:
            sync_hook(interrupted)
        raise
    finally:
        eval_env.close()
        env.close()

    if not completed:  # pragma: no cover - defensive
        raise RuntimeError("training ended without completion")
    final = checkpoint_path(paths.checkpoints, "final", int(model.num_timesteps))
    _save_model(model, final, config)
    if sync_hook:
        sync_hook(final)
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
            STATUS_TRAINING,
            progress={"latest_checkpoint": final.name, "trained_steps": int(model.num_timesteps)},
        )
    return final


def _override(value: str) -> tuple[str, Any]:
    return parse_override(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train an SB3 PPO locomotion policy")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--resume", nargs="?", const="latest")
    parser.add_argument("--set", action="append", default=[], type=_override, dest="overrides")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(args.config, dict(args.overrides))
    if config.backend != "sb3":
        raise SystemExit("selected config is not an SB3 config")
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
        final = train(config, args.run_id, args.runs_root, resume, state=state)
    except (RuntimeError, ValueError) as exc:
        state.update_status(STATUS_FAILED, error=str(exc))
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps({"status": "complete", "checkpoint": str(final)}))


if __name__ == "__main__":
    main()
