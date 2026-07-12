from __future__ import annotations

import subprocess
import time
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
    assert record["schema_version"] == 2
    output = telemetry.write_runtime_record(tmp_path / "runtime.json", record)
    assert "runtime_seconds" in output.read_text()


def test_gpu_samples_capture_activity_between_idle_endpoints() -> None:
    samples = [
        {"available": True, "gpus": [{"utilization_percent": 0, "memory_used_mib": 0}]},
        {"available": True, "gpus": [{"utilization_percent": 91, "memory_used_mib": 61_361}]},
        {"available": True, "gpus": [{"utilization_percent": 2, "memory_used_mib": 61_361}]},
    ]
    summary = telemetry.summarize_gpu_samples(samples, 2.0)
    assert summary == {
        "interval_seconds": 2.0,
        "sample_count": 3,
        "active_sample_count": 2,
        "utilization_percent_mean": 31.0,
        "utilization_percent_max": 91.0,
        "memory_used_mib_max": 61_361.0,
    }
    record = telemetry.runtime_record(
        started_at="start",
        completed_at="end",
        runtime_seconds=6,
        start_gpu=samples[0],
        end_gpu=samples[-1],
        gpu_summary=summary,
        phases=[{"name": "playground_compile_and_train", "duration_seconds": 4}],
    )
    assert record["gpu_utilization_percent"] == 31.0
    assert record["phases"][0]["name"] == "playground_compile_and_train"


def test_gpu_sampler_stops_and_aggregates() -> None:
    snapshots = iter(
        [
            {"available": True, "gpus": [{"utilization_percent": 0, "memory_used_mib": 0}]},
            {"available": True, "gpus": [{"utilization_percent": 75, "memory_used_mib": 100}]},
            {"available": True, "gpus": [{"utilization_percent": 0, "memory_used_mib": 100}]},
        ]
    )
    sampler = telemetry.GpuSampler(0.01, snapshot_fn=lambda: next(snapshots)).start()
    time.sleep(0.012)
    summary = sampler.stop()
    assert summary["sample_count"] == 3
    assert summary["utilization_percent_max"] == 75
