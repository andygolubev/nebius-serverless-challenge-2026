"""FastAPI entrypoint for the SaaS control-plane app.

Serves the auth + job API and (when built) the static frontend. Identity comes from a
bearer session token issued after email one-time-code verification; every job and
artifact is scoped to the session's tenant (the verified email).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from . import catalog
from .auth import AuthService, RateLimited, is_valid_email, normalize_email
from .email_sender import build_email_sender
from .models import (
    STATUS_QUEUED,
    ArtifactManifest,
    AuthRequest,
    Job,
    JobRequest,
    VerifyRequest,
)
from .orchestration import build_backend
from .store import AuthStore, JobStore, Session

app = FastAPI(title="Sim2Policy SaaS", version="0.2.0")
_store = JobStore()
_backend = build_backend(os.environ.get("SAAS_ORCHESTRATION_BACKEND", "mock"))
_auth = AuthService(AuthStore(), build_email_sender(os.environ.get("SAAS_EMAIL_BACKEND", "mock")))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_session(request: Request) -> Session:
    """Resolve `Authorization: Bearer <token>` to a live session or 401."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    session = _auth.resolve_session(token.strip())
    if session is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    return session


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "backend": _backend.name}


# -- auth --


@app.post("/auth/request-code")
def request_code(req: AuthRequest) -> dict[str, str]:
    email = normalize_email(req.email)
    if not is_valid_email(email):
        raise HTTPException(status_code=422, detail="invalid email address")
    try:
        _auth.request_code(email)
    except RateLimited:
        raise HTTPException(status_code=429, detail="too many code requests; try again later")
    # Neutral response: identical whether or not the email has an account.
    return {"status": "sent"}


@app.post("/auth/verify")
def verify_code(req: VerifyRequest) -> dict[str, str]:
    email = normalize_email(req.email)
    token = _auth.verify_code(email, req.code.strip())
    if token is None:
        raise HTTPException(status_code=401, detail="wrong or expired code")
    return {"token": token, "email": email}


@app.post("/auth/logout")
def logout(request: Request) -> dict[str, str]:
    header = request.headers.get("authorization", "")
    _, _, token = header.partition(" ")
    if token:
        _auth.logout(token.strip())
    return {"status": "logged_out"}


@app.get("/me")
def me(session: Session = Depends(require_session)) -> dict[str, str]:
    return {"email": session.email}


# -- jobs --


@app.get("/training-options")
def training_options() -> dict:
    return catalog.serialize()


@app.post("/jobs", status_code=201)
def submit_job(req: JobRequest, session: Session = Depends(require_session)) -> Job:
    try:
        if req.preset is not None:
            expansion = catalog.expand_preset(req.preset)
            params = {**expansion["params"], **req.params}
            if req.seed is not None:
                params.setdefault("seed", req.seed)
            resolved = catalog.resolve_config(expansion["environment"], expansion["algorithm"], params)
        else:
            if req.environment is None or req.algorithm is None:
                raise catalog.ValidationError("environment", "provide a preset, or environment and algorithm")
            params = dict(req.params)
            if req.seed is not None:
                params.setdefault("seed", req.seed)
            resolved = catalog.resolve_config(req.environment, req.algorithm, params)
    except catalog.ValidationError as e:
        raise HTTPException(status_code=422, detail={"field": e.field, "message": e.message})
    job = Job(
        id=uuid.uuid4().hex,
        tenant_id=session.email,
        preset=req.preset,
        environment=resolved["environment"],
        algorithm=resolved["algorithm"],
        resolved_config=resolved,
        status=STATUS_QUEUED,
        created_at=_now(),
        updated_at=_now(),
    )
    _store.put(job)
    _backend.launch(job, _store)
    return job


@app.get("/jobs")
def list_jobs(session: Session = Depends(require_session)) -> list[Job]:
    return _store.list(session.email)


@app.get("/jobs/{job_id}")
def get_job(job_id: str, session: Session = Depends(require_session)) -> Job:
    job = _store.get(session.email, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/jobs/{job_id}/artifacts")
def get_artifacts(job_id: str, session: Session = Depends(require_session)) -> ArtifactManifest:
    # Enforce ownership before returning artifacts.
    if _store.get(session.email, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    manifest = _store.get_artifacts(job_id)
    if manifest is None:
        raise HTTPException(status_code=409, detail="artifacts not ready")
    return manifest


# Serve the built frontend if present (single-image deployment). Kept last so API routes win.
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
