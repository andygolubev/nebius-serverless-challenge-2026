from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import pytest

from sim2policy import render
from sim2policy.checkpoint import checkpoint_path, write_checkpoint_metadata
from sim2policy.config import load_config

ROOT = Path(__file__).parents[1]


class FakeActionSpace:
    def sample(self) -> int:
        return 0


class FakeEnv:
    def __init__(self, terminate_every: int = 2) -> None:
        self.action_space = FakeActionSpace()
        self.terminate_every = terminate_every
        self.steps = 0
        self.reset_seeds: list[int | None] = []
        self.closed = False

    def reset(self, *, seed: int | None = None) -> tuple[int, dict[str, Any]]:
        self.reset_seeds.append(seed)
        self.steps = 0
        return 0, {}

    def step(self, action: Any) -> tuple[int, float, bool, bool, dict[str, Any]]:
        del action
        self.steps += 1
        return 0, 0.0, self.steps >= self.terminate_every, False, {}

    def render(self) -> list[list[list[int]]]:
        return [[[0, 0, 0]]]

    def close(self) -> None:
        self.closed = True


class FakeGym:
    def __init__(self, env: FakeEnv) -> None:
        self.env = env
        self.calls: list[dict[str, Any]] = []

    def make(self, environment: str, **kwargs: Any) -> FakeEnv:
        self.calls.append({"environment": environment, **kwargs})
        return self.env


def make_checkpoint(tmp_path: Path, environment: str = "Pendulum-v1") -> Path:
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    if environment != config.environment:
        config = replace(config, environment=environment)
    checkpoint = checkpoint_path(tmp_path, "final", 128)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"policy")
    write_checkpoint_metadata(checkpoint, config, 128)
    return checkpoint


def test_rollout_resets_across_episode_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = FakeEnv(terminate_every=1)
    gym = FakeGym(env)
    saved: dict[str, Any] = {}

    def fake_import(name: str) -> Any:
        if name == "gymnasium":
            return gym
        if name == "stable_baselines3":
            return type("StableBaselines3", (), {"PPO": object})
        raise ImportError(name)

    monkeypatch.setattr("sim2policy.render.importlib.import_module", fake_import)

    def fake_mimsave(output: Path, frames: list[Any], fps: int) -> None:
        saved["frames"] = frames
        saved["fps"] = fps
        output.write_bytes(b"mp4")

    monkeypatch.setattr(imageio, "mimsave", fake_mimsave)
    config = load_config(ROOT / "configs/smoke_sb3.yaml", {"rendering.frames": 10})
    output = render.render_sb3(None, config, tmp_path / "rollout.mp4", random_policy=True)
    assert output.is_file()
    assert len(saved["frames"]) == 10
    assert env.reset_seeds[:3] == [0, 1, 2]
    assert env.closed


def test_checkpoint_mismatch_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(name: str) -> Any:
        if name == "gymnasium":
            return FakeGym(FakeEnv())
        if name == "stable_baselines3":
            return type("StableBaselines3", (), {"PPO": object})
        raise ImportError(name)

    monkeypatch.setattr("sim2policy.render.importlib.import_module", fake_import)
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    checkpoint = make_checkpoint(tmp_path, "Other-v1")
    with pytest.raises(ValueError, match="checkpoint is for"):
        render.render_sb3(checkpoint, config, tmp_path / "bad.mp4")


def test_make_rgb_env_retries_without_size_for_classic_control() -> None:
    env = FakeEnv()

    class ClassicGym(FakeGym):
        def make(self, environment: str, **kwargs: Any) -> FakeEnv:
            self.calls.append({"environment": environment, **kwargs})
            if "width" in kwargs:
                raise TypeError("unexpected keyword argument 'width'")
            return self.env

    gym = ClassicGym(env)
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    assert render._make_rgb_env(gym, config) is env
    assert "width" in gym.calls[0]
    assert "width" not in gym.calls[1]


def test_fallback_uses_osmesa_after_egl_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del command
        backend = kwargs["env"]["MUJOCO_GL"]
        calls.append(backend)
        return subprocess.CompletedProcess([], 1 if backend == "egl" else 0, "", "boom")

    monkeypatch.setattr("sim2policy.render.subprocess.run", fake_run)
    assert render.render_with_fallback(["--config", "x", "--output", "y"]) == "osmesa"
    assert calls == ["egl", "osmesa"]


def test_montage_command_labels_and_inputs(tmp_path: Path) -> None:
    videos = [tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "c.mp4"]
    command = render.montage_command(videos, tmp_path / "out.mp4")
    assert command[:2] == ["ffmpeg", "-y"]
    assert any("25pct" in part for part in command)
    assert any("hstack=inputs=3" in part for part in command)
