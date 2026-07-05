"""In-memory, tenant-scoped job + artifact store for the mock stage.

A real backend swaps this for the durable S3 run tree; the interface stays the same.
"""

from __future__ import annotations

import threading

from .models import ArtifactManifest, Job


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._artifacts: dict[str, ArtifactManifest] = {}

    def put(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, tenant_id: str, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            # Tenant isolation: never reveal another tenant's job.
            if job is None or job.tenant_id != tenant_id:
                return None
            return job

    def list(self, tenant_id: str) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs.values() if j.tenant_id == tenant_id]

    def set_artifacts(self, manifest: ArtifactManifest) -> None:
        with self._lock:
            self._artifacts[manifest.job_id] = manifest

    def get_artifacts(self, job_id: str) -> ArtifactManifest | None:
        with self._lock:
            return self._artifacts.get(job_id)
