from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import progression_checkpoints, validate_checkpoint
from sim2policy.config import RunConfig, load_config
from sim2policy.storage import ArtifactStore


def _override(value: str) -> tuple[str, Any]:
    key, separator, raw = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("override must be KEY=YAML_VALUE")
    import yaml

    return key, yaml.safe_load(raw)


def _format_override(item: tuple[str, Any]) -> str:
    key, value = item
    return f"{key}={json.dumps(value)}"


def _make_rgb_env(gym: Any, config: RunConfig) -> Any:
    kwargs: dict[str, Any] = {
        "render_mode": "rgb_array",
        "width": config.rendering.width,
        "height": config.rendering.height,
    }
    try:
        return gym.make(config.environment, **kwargs)
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument 'width'" not in message and (
            "unexpected keyword argument 'height'" not in message
        ):
            raise
        return gym.make(config.environment, render_mode="rgb_array")


def render_sb3(
    checkpoint: Path | None, config: RunConfig, output: Path, random_policy: bool = False
) -> Path:
    try:
        import imageio.v2 as imageio

        gym = importlib.import_module("gymnasium")
        PPO = importlib.import_module("stable_baselines3").PPO
    except ImportError as exc:
        raise RuntimeError("rendering requires the sb3/media dependency set") from exc
    model = None
    if not random_policy:
        if checkpoint is None:
            raise ValueError("checkpoint is required")
        validate_checkpoint(checkpoint, config)
        model = PPO.load(checkpoint, device="cpu")
    env = _make_rgb_env(gym, config)
    observation, _ = env.reset(seed=config.rendering.seed)
    frames: list[Any] = []
    reset_count = 0
    for _ in range(config.rendering.frames):
        action = (
            env.action_space.sample()
            if model is None
            else model.predict(observation, deterministic=True)[0]
        )
        observation, _, terminated, truncated, _ = env.step(action)
        frame = env.render()
        if frame is None:
            raise RuntimeError("environment returned no RGB frame")
        frames.append(frame)
        if terminated or truncated:
            reset_count += 1
            observation, _ = env.reset(seed=config.rendering.seed + reset_count)
    env.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(output, frames, fps=config.rendering.fps)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("video encoder produced no output")
    return output


def render_mjx(
    checkpoint: Path | None, config: RunConfig, output: Path, random_policy: bool = False
) -> Path:
    try:
        import imageio.v2 as imageio

        from sim2policy.train_mjx import mjx_policy_session
    except ImportError as exc:
        raise RuntimeError("MJX rendering requires the mjx dependency group") from exc
    if checkpoint is None:
        raise ValueError("checkpoint is required for MJX rendering")
    with mjx_policy_session(checkpoint, config) as (jax, environment, policy):
        reset = jax.jit(environment.reset)
        step = jax.jit(environment.step)
        key = jax.random.PRNGKey(config.rendering.seed)
        state = reset(key)
        trajectory: list[Any] = []
        for _ in range(config.rendering.frames):
            key, action_key = jax.random.split(key)
            if random_policy:
                action = jax.random.uniform(
                    action_key,
                    (environment.action_size,),
                    minval=-1.0,
                    maxval=1.0,
                )
            else:
                action, _ = policy(state.obs, action_key)
            state = step(state, action)
            trajectory.append(state)
            if bool(state.done):
                key, reset_key = jax.random.split(key)
                state = reset(reset_key)
        frames = environment.render(
            trajectory,
            height=config.rendering.height,
            width=config.rendering.width,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(output, frames, fps=config.rendering.fps)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("video encoder produced no output")
    return output


def render_with_fallback(args: list[str]) -> str:
    errors: list[str] = []
    for backend in ("egl", "osmesa"):
        env = os.environ.copy()
        env["MUJOCO_GL"] = backend
        process = subprocess.run(
            [sys.executable, "-m", "sim2policy.render", "--worker", *args],
            env=env,
            text=True,
            capture_output=True,
        )
        if process.returncode == 0:
            return backend
        errors.append(f"{backend}: {process.stderr.strip()}")
    raise RuntimeError("headless rendering failed: " + "; ".join(errors))


def montage_command(videos: list[Path], output: Path) -> list[str]:
    inputs = [part for video in videos for part in ("-i", str(video))]
    labels = ["initial", "25pct", "final"]
    filters = ";".join(
        f"[{i}:v]drawtext=text='{label}':x=20:y=20:fontsize=28:fontcolor=white[v{i}]"
        for i, label in enumerate(labels)
    )
    filters += ";[v0][v1][v2]hstack=inputs=3[out]"
    return ["ffmpeg", "-y", *inputs, "-filter_complex", filters, "-map", "[out]", str(output)]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", default="render")
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--montage", action="store_true")
    parser.add_argument("--checkpoints-dir", type=Path)
    parser.add_argument("--total-steps", type=int)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--set", action="append", default=[], type=_override, dest="overrides")
    args = parser.parse_args(argv)
    config = load_config(args.config, dict(args.overrides))
    override_args = [part for item in args.overrides for part in ("--set", _format_override(item))]
    if args.montage:
        if args.checkpoints_dir is None or args.total_steps is None:
            parser.error("--montage requires --checkpoints-dir and --total-steps")
        checkpoints = progression_checkpoints(args.checkpoints_dir, args.total_steps)
        videos: list[Path] = []
        for label, checkpoint in zip(("initial", "quarter", "final"), checkpoints, strict=True):
            video = args.output.parent / f"{label}-{checkpoint.stem}.mp4"
            render_with_fallback(
                [
                    "--config",
                    args.config,
                    "--checkpoint",
                    str(checkpoint),
                    "--output",
                    str(video),
                    *override_args,
                ]
            )
            videos.append(video)
        subprocess.run(montage_command(videos, args.output), check=True)
        return
    if args.worker:
        if config.backend == "mjx":
            render_mjx(args.checkpoint, config, args.output, args.smoke_test)
        else:
            render_sb3(args.checkpoint, config, args.output, args.smoke_test)
        return
    child = ["--config", args.config, "--output", str(args.output)]
    if args.checkpoint:
        child += ["--checkpoint", str(args.checkpoint)]
    if args.smoke_test:
        child.append("--smoke-test")
    child.extend(override_args)
    backend = render_with_fallback(child)
    store = ArtifactStore(config.storage, args.run_id)
    if store.enabled:
        store.upload_file(args.output, f"videos/{args.output.name}")
    print(f"rendered with {backend}: {args.output}")


if __name__ == "__main__":
    main()
