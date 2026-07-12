from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def gpu_snapshot(timeout_seconds: float = 2.0) -> dict[str, Any]:
    if shutil.which("nvidia-smi") is None:
        return {"available": False, "reason": "nvidia-smi not found", "gpus": []}
    query = "index,name,utilization.gpu,memory.used,memory.total"
    try:
        process = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": type(exc).__name__, "gpus": []}

    gpus: list[dict[str, Any]] = []
    for line in process.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            continue
        index, name, utilization, memory_used, memory_total = parts
        gpus.append(
            {
                "index": int(index),
                "name": name,
                "utilization_percent": float(utilization),
                "memory_used_mib": float(memory_used),
                "memory_total_mib": float(memory_total),
            }
        )
    return {"available": bool(gpus), "reason": None if gpus else "no GPU rows", "gpus": gpus}


def mean_gpu_utilization(snapshot: dict[str, Any]) -> float | None:
    gpus = snapshot.get("gpus") or []
    if not gpus:
        return None
    return sum(float(gpu["utilization_percent"]) for gpu in gpus) / len(gpus)


def summarize_gpu_samples(samples: list[dict[str, Any]], interval_seconds: float) -> dict[str, Any]:
    """Aggregate periodic snapshots without pretending an endpoint is a run average."""
    utilization_samples: list[float] = []
    memory_samples: list[float] = []
    active_samples = 0
    for snapshot in samples:
        gpus = snapshot.get("gpus") or []
        if not gpus:
            continue
        utilization = sum(float(gpu["utilization_percent"]) for gpu in gpus) / len(gpus)
        utilization_samples.append(utilization)
        memory_samples.append(max(float(gpu["memory_used_mib"]) for gpu in gpus))
        if utilization > 0:
            active_samples += 1
    return {
        "interval_seconds": interval_seconds,
        "sample_count": len(utilization_samples),
        "active_sample_count": active_samples,
        "utilization_percent_mean": (
            sum(utilization_samples) / len(utilization_samples)
            if utilization_samples
            else None
        ),
        "utilization_percent_max": max(utilization_samples) if utilization_samples else None,
        "memory_used_mib_max": max(memory_samples) if memory_samples else None,
    }


class GpuSampler:
    """Collect `nvidia-smi` snapshots on a daemon thread for a bounded process lifetime."""

    def __init__(
        self,
        interval_seconds: float = 2.0,
        snapshot_fn: Any = gpu_snapshot,
    ) -> None:
        self.interval_seconds = interval_seconds
        self._snapshot_fn = snapshot_fn
        self._samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _sample(self) -> None:
        snapshot = self._snapshot_fn()
        with self._lock:
            self._samples.append(snapshot)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()

    def start(self) -> GpuSampler:
        if self._thread is not None:
            return self
        self._sample()
        self._thread = threading.Thread(target=self._run, name="gpu-sampler", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict[str, Any]:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=max(self.interval_seconds * 2, 1.0))
            self._sample()
            self._thread = None
        return self.summary()

    @property
    def samples(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._samples)

    def summary(self) -> dict[str, Any]:
        return summarize_gpu_samples(self.samples, self.interval_seconds)


def runtime_record(
    *,
    started_at: str,
    completed_at: str,
    runtime_seconds: float,
    start_gpu: dict[str, Any],
    end_gpu: dict[str, Any],
    gpu_summary: dict[str, Any] | None = None,
    phases: list[dict[str, Any]] | None = None,
    outcome: str = "completed",
) -> dict[str, Any]:
    utilization = (
        gpu_summary.get("utilization_percent_mean")
        if gpu_summary is not None
        else mean_gpu_utilization(end_gpu)
    )
    return {
        "schema_version": 2,
        "started_at": started_at,
        "completed_at": completed_at,
        "runtime_seconds": runtime_seconds,
        "outcome": outcome,
        "gpu_start": start_gpu,
        "gpu_end": end_gpu,
        "gpu_utilization_percent": utilization,
        "gpu_summary": gpu_summary,
        "phases": phases or [],
    }


def write_runtime_record(output: Path, record: dict[str, Any]) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def monotonic_seconds() -> float:
    return time.monotonic()
