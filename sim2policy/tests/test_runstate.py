from __future__ import annotations

from pathlib import Path

import pytest

from sim2policy.config import StorageConfig
from sim2policy.runstate import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_TRAINING,
    RunStateStore,
)


def store(tmp_path: Path) -> RunStateStore:
    return RunStateStore(StorageConfig(mode="local"), "ant-demo-20260629-abc123", tmp_path)


def test_init_and_read_status(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.init_status(preset="ant-demo")
    status = state.read_status()
    assert status is not None
    assert status.status == STATUS_QUEUED
    assert status.preset == "ant-demo"
    assert status.progress["phase"] == STATUS_QUEUED


def test_status_transitions_preserve_created_at(tmp_path: Path) -> None:
    state = store(tmp_path)
    initial = state.init_status(preset="ant-demo")
    state.update_status(STATUS_TRAINING, progress={"latest_checkpoint": "step-100.zip"})
    completed = state.update_status(STATUS_COMPLETED, progress={"latest_mean_reward": 12.5})
    assert completed.created_at == initial.created_at
    assert completed.status == STATUS_COMPLETED
    # progress accumulates across transitions
    assert completed.progress["latest_checkpoint"] == "step-100.zip"
    assert completed.progress["latest_mean_reward"] == 12.5
    assert completed.progress["phase"] == STATUS_COMPLETED


def test_failure_recorded(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.init_status(preset="ant-demo")
    failed = state.update_status(STATUS_FAILED, error="boom")
    assert failed.status == STATUS_FAILED
    assert failed.error == "boom"
    assert state.read_status().error == "boom"


def test_unknown_status_rejected(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.init_status(preset="ant-demo")
    with pytest.raises(ValueError):
        state.update_status("paused")


def test_request_round_trips(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.write_request({"preset": "ant-demo", "safe_params": {"seed": 3}})
    assert state.read_request()["safe_params"]["seed"] == 3


def test_manifest_and_artifact_urls(tmp_path: Path) -> None:
    state = store(tmp_path)
    # create two artifacts on disk
    (state.run_root / "checkpoints").mkdir(parents=True)
    (state.run_root / "checkpoints" / "final.zip").write_bytes(b"policy")
    (state.run_root / "report").mkdir(parents=True)
    (state.run_root / "report" / "metrics.json").write_text("{}", encoding="utf-8")

    discovered = state.discover_artifacts()
    assert discovered == {
        "final_policy": "checkpoints/final.zip",
        "metrics_json": "report/metrics.json",
    }
    state.write_manifest(discovered)
    urls = state.artifact_urls()
    assert set(urls) == {"final_policy", "metrics_json"}
    assert urls["final_policy"].endswith("checkpoints/final.zip")  # local path


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert store(tmp_path).read_status() is None
    assert store(tmp_path).read_manifest() == {}
