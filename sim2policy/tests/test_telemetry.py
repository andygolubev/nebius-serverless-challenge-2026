from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from sim2policy import telemetry


def test_gpu_snapshot_unavailable_without_nvidia_smi(monkeypatch: Any) -> None:
    monkeypatch.setattr("sim2policy.telemetry.shutil.which", lambda _: None)
    snapshot = telemetry.gpu_snapshot()
    assert snapshot == {"available": False, "reason": "nvidia-smi not found", "gpus": []}
    assert telemetry.mean_gpu_utilization(snapshot) is None


def test_gpu_snapshot_parses_nvidia_smi(monkeypatch: Any) -> None:
    monkeypatch.setattr("sim2policy.telemetry.shutil.which", lambda _: "/usr/bin/nvidia-smi")

    def fake_run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, "0, NVIDIA L4, 42, 1024, 23034\n", "")

    monkeypatch.setattr("sim2policy.telemetry.subprocess.run", fake_run)
    snapshot = telemetry.gpu_snapshot()
    assert snapshot["available"] is True
    assert snapshot["gpus"][0]["name"] == "NVIDIA L4"
    assert telemetry.mean_gpu_utilization(snapshot) == 42.0


def test_runtime_record_writes_unavailable_values(tmp_path: Path) -> None:
    unavailable = {"available": False, "reason": "nope", "gpus": []}
    record = telemetry.runtime_record(
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:00:01Z",
        runtime_seconds=1.0,
        start_gpu=unavailable,
        end_gpu=unavailable,
    )
    assert record["gpu_utilization_percent"] is None
    output = telemetry.write_runtime_record(tmp_path / "runtime.json", record)
    assert "runtime_seconds" in output.read_text()
