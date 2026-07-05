"""FastAPI entrypoint for the SaaS control-plane app.

Serves the job API and (when built) the static frontend. Tenant identity comes from the
`X-Tenant-Id` header; every job and artifact is scoped to that tenant.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from .models import (
    STATUS_QUEUED,
    ArtifactManifest,
    Job,
    JobRequest,
)
from .orchestration import build_backend
from .store import JobStore

# Allowlisted presets — no custom code/images/environments accepted (mirrors demo API).
ALLOWED_PRESETS = {"halfcheetah-demo", "ant-demo", "ant-quality", "go1-mjx-demo"}

app = FastAPI(title="Sim2Policy SaaS", version="0.1.0")
_store = JobStore()
_backend = build_backend(os.environ.get("SAAS_ORCHESTRATION_BACKEND", "mock"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tenant(x_tenant_id: str | None) -> str:
    # A real deployment authenticates this (API key / OIDC). For the mock stage we accept
    # the header and default to "demo".
    return x_tenant_id or "demo"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "backend": _backend.name}


@app.get("/training-options")
def training_options() -> dict[str, list[str]]:
    return {"presets": sorted(ALLOWED_PRESETS)}


@app.post("/jobs", status_code=201)
def submit_job(req: JobRequest, x_tenant_id: str | None = Header(default=None)) -> Job:
    if req.preset not in ALLOWED_PRESETS:
        raise HTTPException(status_code=422, detail=f"unknown preset: {req.preset}")
    tenant = _tenant(x_tenant_id)
    job = Job(
        id=uuid.uuid4().hex,
        tenant_id=tenant,
        preset=req.preset,
        seed=req.seed,
        status=STATUS_QUEUED,
        created_at=_now(),
        updated_at=_now(),
    )
    _store.put(job)
    _backend.launch(job, _store)
    return job


@app.get("/jobs")
def list_jobs(x_tenant_id: str | None = Header(default=None)) -> list[Job]:
    return _store.list(_tenant(x_tenant_id))


@app.get("/jobs/{job_id}")
def get_job(job_id: str, x_tenant_id: str | None = Header(default=None)) -> Job:
    job = _store.get(_tenant(x_tenant_id), job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/jobs/{job_id}/artifacts")
def get_artifacts(job_id: str, x_tenant_id: str | None = Header(default=None)) -> ArtifactManifest:
    # Enforce ownership before returning artifacts.
    if _store.get(_tenant(x_tenant_id), job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    manifest = _store.get_artifacts(job_id)
    if manifest is None:
        raise HTTPException(status_code=409, detail="artifacts not ready")
    return manifest


# Serve the built frontend if present (single-image deployment). Kept last so API routes win.
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
