from pathlib import Path

import pytest

from sim2policy.checkpoint import (
    CheckpointError,
    checkpoint_path,
    latest_checkpoint,
    nearest_checkpoint,
    progression_checkpoints,
    validate_checkpoint,
    write_checkpoint_metadata,
)
from sim2policy.config import load_config

ROOT = Path(__file__).parents[1]


def make_checkpoint(directory: Path, kind: str, step: int) -> Path:
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    path = checkpoint_path(directory, kind, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"checkpoint-{step}".encode())
    write_checkpoint_metadata(path, config, step)
    return path


def test_checkpoint_round_trip_and_latest(tmp_path: Path) -> None:
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    make_checkpoint(tmp_path, "initial", 0)
    expected = make_checkpoint(tmp_path, "step", 128)
    assert latest_checkpoint(tmp_path) == expected
    assert validate_checkpoint(expected, config).step == 128


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    path = make_checkpoint(tmp_path, "step", 128)
    path.write_bytes(b"tampered")
    with pytest.raises(CheckpointError, match="checksum"):
        validate_checkpoint(path, config)


def test_progression_uses_nearest_quarter(tmp_path: Path) -> None:
    initial = make_checkpoint(tmp_path, "initial", 0)
    near_quarter = make_checkpoint(tmp_path, "step", 30)
    final = make_checkpoint(tmp_path, "final", 100)
    assert progression_checkpoints(tmp_path, 100) == (initial, near_quarter, final)


def test_nearest_checkpoint_picks_closest_step_and_breaks_ties_earlier(tmp_path: Path) -> None:
    near_gate = make_checkpoint(tmp_path / "closest", "step", 98)
    make_checkpoint(tmp_path / "closest", "step", 150)
    assert nearest_checkpoint(tmp_path / "closest", 100) == near_gate

    tie_low = make_checkpoint(tmp_path / "tie", "step", 90)
    make_checkpoint(tmp_path / "tie", "step", 110)
    assert nearest_checkpoint(tmp_path / "tie", 100) == tie_low
