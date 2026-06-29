from __future__ import annotations

import json
import shutil
import subprocess
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


def runtime_record(
    *,
    started_at: str,
    completed_at: str,
    runtime_seconds: float,
    start_gpu: dict[str, Any],
    end_gpu: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "started_at": started_at,
        "completed_at": completed_at,
        "runtime_seconds": runtime_seconds,
        "gpu_start": start_gpu,
        "gpu_end": end_gpu,
        "gpu_utilization_percent": mean_gpu_utilization(end_gpu),
    }


def write_runtime_record(output: Path, record: dict[str, Any]) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def monotonic_seconds() -> float:
    return time.monotonic()
