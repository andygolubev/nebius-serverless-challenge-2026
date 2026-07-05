"""Pluggable job orchestration. Only `mock` exists now; a Nebius Serverless backend
plugs in later without changing the tenant-facing API.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Protocol

from .models import (
    LIFECYCLE,
    STATUS_COMPLETED,
    ArtifactManifest,
    Job,
)
from .store import JobStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestrationBackend(Protocol):
    name: str

    def launch(self, job: Job, store: JobStore) -> None: ...


class MockBackend:
    """Walk a job through the full lifecycle and write placeholder artifacts.

    No Nebius credentials or GPU required. `step_delay` keeps demos fast.
    """

    name = "mock"

    def __init__(self, step_delay: float = 0.5) -> None:
        self.step_delay = step_delay

    def launch(self, job: Job, store: JobStore) -> None:
        thread = threading.Thread(target=self._run, args=(job, store), daemon=True)
        thread.start()

    def _run(self, job: Job, store: JobStore) -> None:
        for status in LIFECYCLE:
            time.sleep(self.step_delay)
            job = job.model_copy(update={"status": status, "updated_at": _now()})
            store.put(job)
        store.set_artifacts(
            ArtifactManifest(
                job_id=job.id,
                status=STATUS_COMPLETED,
                metrics={"mean_reward": 1234.5, "steps": 100000, "mock": True},
                media=[f"runs/{job.id}/videos/rollout.mp4"],
            )
        )


def build_backend(name: str) -> OrchestrationBackend:
    if name == "mock":
        return MockBackend()
    raise ValueError(f"unknown orchestration backend: {name!r}")
