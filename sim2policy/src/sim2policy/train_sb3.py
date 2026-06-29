from __future__ import annotations

import argparse
import json
import sys
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


def _imports() -> tuple[Any, Any, Any]:
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.callbacks import BaseCallback
        from stable_baselines3.common.env_util import make_vec_env
    except ImportError as exc:
        raise RuntimeError(
            "SB3 dependencies are unavailable; install with `uv sync --extra sb3` "
            "or use the SB3 container target"
        ) from exc
    return PPO, BaseCallback, make_vec_env


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
) -> Any:
    _, BaseCallback, _ = _imports()

    class DurableCheckpointCallback(BaseCallback):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__(verbose=0)
            self.next_step = (
                ((int(self.model.num_timesteps) // config.checkpoint.every_steps) + 1)
                * config.checkpoint.every_steps
                if hasattr(self, "model")
                else config.checkpoint.every_steps
            )

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

    return DurableCheckpointCallback()


def train(
    config: RunConfig,
    run_id: str,
    runs_root: Path,
    resume: Path | None = None,
    sync_hook: Callable[[Path], None] | None = None,
) -> Path:
    PPO, _, make_vec_env = _imports()
    paths = create_run_paths(run_id, runs_root)
    write_metadata(paths, run_id, config, {"requested": config.training.device})
    env = make_vec_env(
        config.environment,
        n_envs=config.training.n_envs,
        seed=config.seed,
    )
    if resume:
        resume_metadata = validate_checkpoint(resume, config)
        model = PPO.load(resume, env=env, device=config.training.device)
        if int(model.num_timesteps) != resume_metadata.step:
            raise RuntimeError("checkpoint timestep does not match its metadata")
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
        reset_num_timesteps = True

    callback = build_checkpoint_callback(config, paths, sync_hook)
    completed = False
    try:
        model.learn(
            total_timesteps=config.training.total_steps,
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
        env.close()

    if not completed:  # pragma: no cover - defensive
        raise RuntimeError("training ended without completion")
    final = checkpoint_path(paths.checkpoints, "final", int(model.num_timesteps))
    _save_model(model, final, config)
    if sync_hook:
        sync_hook(final)
    return final


def _override(value: str) -> tuple[str, Any]:
    key, separator, raw = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("override must be KEY=YAML_VALUE")
    return key, yaml.safe_load(raw)


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
        resume = (
            latest_checkpoint(args.runs_root / args.run_id / "checkpoints")
            if args.resume == "latest"
            else Path(args.resume)
        )
    try:
        final = train(config, args.run_id, args.runs_root, resume)
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps({"status": "complete", "checkpoint": str(final)}))


if __name__ == "__main__":
    main()
