from pathlib import Path

import pytest

from sim2policy.config import (
    ConfigError,
    load_config,
    redact_mapping,
    validate_prefix,
    validate_run_id,
)
from sim2policy.run import create_run_paths, write_metadata
from sim2policy.train_mjx import _override as mjx_override
from sim2policy.train_sb3 import _override as sb3_override

ROOT = Path(__file__).parents[1]


def test_load_and_override_config() -> None:
    config = load_config(ROOT / "configs/smoke_sb3.yaml", {"training.total_steps": 512, "seed": 7})
    assert config.training.total_steps == 512
    assert config.seed == 7
    assert config.backend == "sb3"


@pytest.mark.parametrize("parser", [sb3_override, mjx_override])
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
