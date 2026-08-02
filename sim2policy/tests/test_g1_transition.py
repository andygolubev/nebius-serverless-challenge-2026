from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from sim2policy.checkpoint import checkpoint_path, write_checkpoint_metadata
from sim2policy.config import load_config
from sim2policy.g1_transition import (
    TransitionError,
    build_transition_record,
    verify_transition_record,
    write_immutable_local,
)

ROOT = Path(__file__).parents[1]


def _checkpoint(tmp_path: Path):
    config = load_config(
        ROOT / "configs/g1_forward_flat_mjx.yaml",
        {"training.total_steps": 149_422_080},
    )
    checkpoint = checkpoint_path(tmp_path, "final", 149_422_080)
    with zipfile.ZipFile(checkpoint, "w") as archive:
        archive.writestr("manifest.ocdbt", "test")
    write_checkpoint_metadata(checkpoint, config, 149_422_080)
    return config, checkpoint


def _record(tmp_path: Path):
    _, checkpoint = _checkpoint(tmp_path)
    record = build_transition_record(
        parent_checkpoint=checkpoint,
        parent_object_key="sim2policy/run-flat/checkpoints/" + checkpoint.name,
        parent_sidecar_key="sim2policy/run-flat/checkpoints/" + checkpoint.name + ".json",
        target_run_id="run-rough",
        trainer_load_path="/runs/run-rough/resume/" + checkpoint.stem,
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        flat_config_digest="c" * 64,
        rough_config_digest="d" * 64,
        measured_flat_steps=149_422_080,
        remaining_rough_budget=300_577_920,
        requested_rough_steps=300_318_720,
    )
    return checkpoint, record


def test_transition_binds_exact_parent_budget_and_declared_reinitialization(tmp_path: Path) -> None:
    checkpoint, record = _record(tmp_path)
    rough = load_config(
        ROOT / "configs/g1_forward_rough_mjx.yaml",
        {"training.total_steps": 300_318_720},
    )
    verify_transition_record(
        record,
        parent_checkpoint=checkpoint,
        target_config=rough,
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        flat_config_digest="c" * 64,
        rough_config_digest="d" * 64,
        target_run_id="run-rough",
        trainer_load_path="/runs/run-rough/resume/" + checkpoint.stem,
    )
    assert record["restore"]["restored_components"] == [
        "observation_normalizer",
        "policy_parameters",
        "value_parameters",
    ]
    assert record["budget"]["requested_rough_steps"] == 300_318_720


def test_transition_rejects_digest_or_load_path_mismatch(tmp_path: Path) -> None:
    checkpoint, record = _record(tmp_path)
    rough = load_config(ROOT / "configs/g1_forward_rough_mjx.yaml")
    record["parent"]["sha256"] = "0" * 64
    with pytest.raises(TransitionError, match="parent bytes"):
        verify_transition_record(
            record,
            parent_checkpoint=checkpoint,
            target_config=rough,
            matrix_digest="a" * 64,
            image_digest="sha256:" + "b" * 64,
            flat_config_digest="c" * 64,
            rough_config_digest="d" * 64,
            target_run_id="run-rough",
            trainer_load_path="/runs/run-rough/resume/" + checkpoint.stem,
        )


def test_local_transition_is_create_once_and_identical_replay_only(tmp_path: Path) -> None:
    _, record = _record(tmp_path)
    path = tmp_path / "transition.json"
    write_immutable_local(path, record)
    write_immutable_local(path, record)
    changed = json.loads(json.dumps(record))
    changed["budget"]["requested_rough_steps"] -= 1
    with pytest.raises(TransitionError, match="different bytes"):
        write_immutable_local(path, changed)
