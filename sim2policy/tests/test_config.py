from pathlib import Path

import pytest

from sim2policy.config import (
    ConfigError,
    load_config,
    parse_override,
    redact_mapping,
    validate_prefix,
    validate_run_id,
)
from sim2policy.evaluate import _override as evaluate_override
from sim2policy.finalize import _override as finalize_override
from sim2policy.render import _override as render_override
from sim2policy.run import create_run_paths, write_metadata
from sim2policy.train_mjx import _override as mjx_override
from sim2policy.train_sb3 import _override as sb3_override

ROOT = Path(__file__).parents[1]


def test_load_and_override_config() -> None:
    config = load_config(ROOT / "configs/smoke_sb3.yaml", {"training.total_steps": 512, "seed": 7})
    assert config.training.total_steps == 512
    assert config.seed == 7
    assert config.backend == "sb3"


@pytest.mark.parametrize(
    "parser",
    [
        parse_override,
        sb3_override,
        mjx_override,
        evaluate_override,
        render_override,
        finalize_override,
    ],
)
def test_serverless_iso_date_override_remains_json_safe(parser) -> None:
    assert parser("reporting.rate_date=2026-07-14") == (
        "reporting.rate_date",
        "2026-07-14",
    )


@pytest.mark.parametrize("run_id", ["../escape", "/absolute", "bad/run", "", ".", ".."])
def test_rejects_unsafe_run_id(run_id: str) -> None:
    with pytest.raises(ConfigError):
        validate_run_id(run_id)


@pytest.mark.parametrize("prefix", ["../escape", "/absolute", "two//parts", "a/../b", "trail/"])
def test_rejects_unsafe_prefix(prefix: str) -> None:
    with pytest.raises(ConfigError):
        validate_prefix(prefix)


def test_unknown_override_is_rejected() -> None:
    with pytest.raises(ConfigError, match="unsupported override"):
        load_config(ROOT / "configs/smoke_sb3.yaml", {"not.real": 1})


def test_rejects_incompatible_mjx_batch_geometry() -> None:
    with pytest.raises(ConfigError, match="must be divisible by n_envs"):
        load_config(
            ROOT / "configs/go1_mjx.yaml",
            {
                "training.n_envs": 4096,
                "training.hyperparameters": {
                    "impl": "jax",
                    "batch_size": 256,
                    "num_minibatches": 8,
                },
            },
        )


def test_g1_uses_pinned_playground_tuned_profile() -> None:
    config = load_config(ROOT / "configs/g1_mjx.yaml")

    assert config.training.total_steps == 200_000_000
    assert config.training.n_envs == 8192
    assert config.checkpoint.every_steps == 11_000_000
    assert config.checkpoint.keep == 20
    assert config.training.hyperparameters == {
        "impl": "jax",
        "num_eval_envs": 128,
        "batch_size": 256,
        "num_minibatches": 32,
        "num_updates_per_batch": 4,
        "unroll_length": 20,
        "episode_length": 1000,
        "learning_rate": 0.0003,
        "entropy_cost": 0.005,
        "discounting": 0.97,
        "reward_scaling": 1.0,
        "action_repeat": 1,
        "clipping_epsilon": 0.2,
        "max_grad_norm": 1.0,
        "policy_obs_key": "state",
        "value_obs_key": "privileged_state",
        "policy_hidden_layer_sizes": [512, 256, 128],
        "value_hidden_layer_sizes": [512, 256, 128],
    }


@pytest.mark.parametrize("target", [0.0, -1.0, 0.4])
def test_rejects_invalid_locomotion_target_velocity(target: float) -> None:
    with pytest.raises(ConfigError, match="target_velocity"):
        load_config(ROOT / "configs/go1_mjx.yaml", {"success.target_velocity": target})


def test_redacts_nested_secrets() -> None:
    assert redact_mapping({"token": "secret", "nested": {"password": "secret"}}) == {
        "token": "<redacted>",
        "nested": {"password": "<redacted>"},
    }


def test_paths_and_metadata(tmp_path: Path) -> None:
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    paths = create_run_paths("safe-run", tmp_path)
    metadata = write_metadata(paths, "safe-run", config)
    assert metadata.is_file()
    artifact_dirs = ("checkpoints", "tensorboard", "videos", "report")
    assert all((paths.root / name).is_dir() for name in artifact_dirs)
