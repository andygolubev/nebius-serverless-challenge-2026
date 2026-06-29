from __future__ import annotations

import importlib.util
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sim2policy.config import load_config
from sim2policy.evaluate import evaluate
from sim2policy.run import create_run_paths
from sim2policy.train_mjx import build_playground_command, train_mjx

ROOT = Path(__file__).parents[1]


def test_build_playground_command_maps_config_to_explicit_flags(tmp_path: Path) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "training.total_steps": 1024,
            "training.n_envs": 32,
        },
    )
    paths = create_run_paths("mjx-command", tmp_path)
    command = build_playground_command(config, paths)
    assert command[:5] == [
        "train-jax-ppo",
        "--env_name=Go1JoystickFlatTerrain",
        "--impl=jax",
        "--seed=0",
        "--num_timesteps=1024",
    ]
    assert "--num_envs=32" in command
    assert "--logdir=" + str(paths.root / "mjx_logs") in command
    assert "--playground_config_overrides" in command
    assert '{"impl":"jax"}' in command
    assert "--policy_hidden_layer_sizes=512,256,128" in command


def test_build_playground_command_rejects_unknown_hyperparameters(tmp_path: Path) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {"training.hyperparameters": {"impl": "jax", "surprise": 1}},
    )
    paths = create_run_paths("mjx-bad-command", tmp_path)
    with pytest.raises(RuntimeError, match="unsupported MJX hyperparameter"):
        build_playground_command(config, paths)


def test_train_mjx_archives_latest_raw_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "training.total_steps": 128,
            "training.n_envs": 4,
            "storage.mode": "local",
        },
    )

    monkeypatch.setattr(
        "sim2policy.train_mjx.validate_mjx_environment",
        lambda config: {"environment": config.environment, "impl": "jax"},
    )

    checkpoint = train_mjx(config, "mjx-run", tmp_path, runner=_fake_checkpoint_runner("64", "128"))
    assert (tmp_path / "mjx-run/checkpoints/step-000000000064.zip").is_file()
    assert checkpoint.name == "final-000000000128.zip"
    assert checkpoint.is_file()
    assert checkpoint.with_suffix(".zip.json").is_file()


def test_train_mjx_extracts_zipped_resume_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "training.total_steps": 256,
            "training.n_envs": 4,
            "storage.mode": "local",
        },
    )
    monkeypatch.setattr(
        "sim2policy.train_mjx.validate_mjx_environment",
        lambda config: {"environment": config.environment, "impl": "jax"},
    )
    resume = train_mjx(config, "mjx-first", tmp_path, runner=_fake_checkpoint_runner("128"))

    seen_command: list[str] = []

    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        seen_command.extend(command)
        return _fake_checkpoint_runner("256")(command, **_)

    train_mjx(config, "mjx-resume", tmp_path, resume=resume, runner=runner)
    load_flag = next(part for part in seen_command if part.startswith("--load_checkpoint_path="))
    resume_path = Path(load_flag.removeprefix("--load_checkpoint_path="))
    assert resume_path.is_dir()
    assert (resume_path / "manifest.ocdbt").is_file()


def test_locomotion_success_reporting_for_mjx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "evaluation.episodes": 2,
            "storage.mode": "local",
        },
    )
    checkpoint = tmp_path / "checkpoint.zip"
    checkpoint.write_bytes(b"fake")

    def fake_evaluate_mjx(checkpoint: Path, config: object) -> tuple[list[dict[str, Any]], float]:
        return (
            [
                {"index": 0, "seed": 0, "reward": 1.0, "length": 50, "success": True},
                {"index": 1, "seed": 1, "reward": 2.0, "length": 50, "success": True},
            ],
            3.5,
        )

    monkeypatch.setattr("sim2policy.train_mjx.evaluate_mjx", fake_evaluate_mjx)
    metrics = evaluate(checkpoint, config, "mjx-report", tmp_path)
    assert metrics["success"] == {
        "met": True,
        "criterion": "velocity >= 0.5 and not fallen",
    }


def test_mjx_backend_stays_optional_in_base_environment() -> None:
    if importlib.util.find_spec("jax") is not None:  # pragma: no cover - optional env
        pytest.skip("MJX optional dependencies are installed in this environment")
    with pytest.raises(RuntimeError, match="uv sync --extra mjx"):
        from sim2policy.train_mjx import require_mjx

        require_mjx()


def _fake_checkpoint_runner(*steps: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        logdir = next(
            part.removeprefix("--logdir=")
            for part in command
            if part.startswith("--logdir=")
        )
        for step in steps:
            checkpoint_dir = Path(logdir) / "experiment" / "checkpoints" / step
            checkpoint_dir.mkdir(parents=True)
            (checkpoint_dir / "manifest.ocdbt").write_text("fake", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    return runner
