from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import progression_checkpoints, validate_checkpoint
from sim2policy.config import RunConfig, load_config
from sim2policy.storage import ArtifactStore


def render_sb3(checkpoint: Path | None, config: RunConfig, output: Path, random_policy: bool = False) -> Path:
    try:
        import gymnasium as gym  # type: ignore[import-not-found]
        import imageio.v2 as imageio  # type: ignore[import-not-found]
        from stable_baselines3 import PPO  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("rendering requires the sb3/media dependency set") from exc
    model = None
    if not random_policy:
        if checkpoint is None:
            raise ValueError("checkpoint is required")
        validate_checkpoint(checkpoint, config)
        model = PPO.load(checkpoint, device="cpu")
    env = gym.make(config.environment, render_mode="rgb_array", width=config.rendering.width, height=config.rendering.height)
    observation, _ = env.reset(seed=config.rendering.seed)
    frames: list[Any] = []
    reset_count = 0
    for _ in range(config.rendering.frames):
        action = env.action_space.sample() if model is None else model.predict(observation, deterministic=True)[0]
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


def render_with_fallback(args: list[str]) -> str:
    errors: list[str] = []
    for backend in ("egl", "osmesa"):
        env = os.environ.copy()
        env["MUJOCO_GL"] = backend
        process = subprocess.run([sys.executable, "-m", "sim2policy.render", "--worker", *args], env=env, text=True, capture_output=True)
        if process.returncode == 0:
            return backend
        errors.append(f"{backend}: {process.stderr.strip()}")
    raise RuntimeError("headless rendering failed: " + "; ".join(errors))


def montage_command(videos: list[Path], output: Path) -> list[str]:
    inputs = [part for video in videos for part in ("-i", str(video))]
    labels = ["initial", "~25%", "final"]
    filters = ";".join(f"[{i}:v]drawtext=text='{label}':x=20:y=20:fontsize=28:fontcolor=white[v{i}]" for i, label in enumerate(labels))
    filters += ";[v0][v1][v2]hstack=inputs=3[out]"
    return ["ffmpeg", "-y", *inputs, "-filter_complex", filters, "-map", "[out]", str(output)]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", default="render")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.worker:
        render_sb3(args.checkpoint, config, args.output, args.smoke_test)
        return
    child = ["--config", args.config, "--output", str(args.output)]
    if args.checkpoint:
        child += ["--checkpoint", str(args.checkpoint)]
    if args.smoke_test:
        child.append("--smoke-test")
    backend = render_with_fallback(child)
    print(f"rendered with {backend}: {args.output}")


if __name__ == "__main__":
    main()

