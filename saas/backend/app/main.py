"""FastAPI entrypoint for the SaaS control-plane app.

Serves the auth + job API and (when built) the static frontend. Identity comes from a
bearer session token issued after email one-time-code verification; every job and
artifact is scoped to the session's tenant (the verified email).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import catalog
from .auth import AuthService, RateLimited, is_valid_email, normalize_email
from .email_sender import EmailDeliveryError, build_email_sender
from .models import (
    STATUS_COMPLETED,
    STATUS_QUEUED,
    Artifact,
    ArtifactManifest,
    AuthRequest,
    Job,
    JobRequest,
    VerifyRequest,
)
from .orchestration import build_backend
from .store import AuthStore, JobStore, Session
from .db import resolve_path

app = FastAPI(title="Sim2Policy SaaS", version="0.2.0")
log = logging.getLogger(__name__)
# Durable state lives in SQLite at SAAS_DB_PATH (a PVC in the cluster); defaults to a
# local file for development.
_db_path = resolve_path()
_store = JobStore(_db_path)
_backend = build_backend(os.environ.get("SAAS_ORCHESTRATION_BACKEND", "mock"))
_auth = AuthService(AuthStore(_db_path), build_email_sender(os.environ.get("SAAS_EMAIL_BACKEND", "mock")))


@app.on_event("startup")
def resume_jobs() -> None:
    resume = getattr(_backend, "resume", None)
    if resume is not None:
        resume(_store)


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
    return {
        "status": "ok",
        "backend": _backend.name,
        "email_backend": _auth.sender.name,
        "email_ready": "true",
    }


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
    except EmailDeliveryError:
        raise HTTPException(
            status_code=503,
            detail="email delivery temporarily unavailable; try again later",
            headers={"Retry-After": "60"},
        )
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
def get_artifacts(job_id: str, session: Session = Depends(require_session)) -> dict:
    # Enforce ownership before returning artifacts.
    job = _store.get(session.email, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    manifest = _store.get_artifacts(job_id)
    if manifest is None:
        manifest = _recover_artifacts(job)
    if manifest is None:
        raise HTTPException(status_code=409, detail="artifacts not ready")
    manifest = _normalize_legacy_manifest(manifest)
    data = manifest.model_dump(exclude={"artifacts": {"__all__": {"key"}}})
    data["media"] = []
    reader = getattr(_backend, "artifact_reader", None)
    for artifact, stored in zip(data["artifacts"], manifest.artifacts, strict=True):
        if reader is not None and hasattr(reader, "presigned_url"):
            artifact["url"] = reader.presigned_url(stored.key, content_type=stored.content_type)
            artifact["download_url"] = reader.presigned_url(stored.key, content_type=stored.content_type, download_name=stored.key.rsplit("/", 1)[-1])
        else:
            artifact["url"] = f"/jobs/{job_id}/artifacts/{artifact['id']}"
            artifact["download_url"] = f"/jobs/{job_id}/artifacts/{artifact['id']}?download=true"
    return data


@app.get("/jobs/{job_id}/artifacts/{artifact_id}")
def access_artifact(job_id: str, artifact_id: str, download: bool = False, session: Session = Depends(require_session)):
    job = _store.get(session.email, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    manifest = _store.get_artifacts(job_id) or _recover_artifacts(job)
    if manifest is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    manifest = _normalize_legacy_manifest(manifest)
    artifact = next((item for item in manifest.artifacts if item.id == artifact_id), None)
    reader = getattr(_backend, "artifact_reader", None)
    if artifact is None or reader is None or not hasattr(reader, "presigned_url"):
        raise HTTPException(status_code=404, detail="artifact not found")
    filename = artifact.key.rsplit("/", 1)[-1] if download else None
    return RedirectResponse(reader.presigned_url(artifact.key, content_type=artifact.content_type, download_name=filename), status_code=307)


def _normalize_legacy_manifest(manifest: ArtifactManifest) -> ArtifactManifest:
    if manifest.artifacts or not manifest.media:
        return manifest
    artifacts = []
    for index, key in enumerate(manifest.media):
        if not isinstance(key, str) or ".." in key.split("/"):
            continue
        filename = key.rsplit("/", 1)[-1]
        stem = filename.rsplit(".", 1)[0]
        artifacts.append(Artifact(id=f"legacy-{index}-{stem}", name=stem.replace("_", " ").replace("-", " ").title(), kind="video" if filename.endswith(".mp4") else "file", content_type="video/mp4" if filename.endswith(".mp4") else "application/octet-stream", key=key))
    normalized = manifest.model_copy(update={"artifacts": artifacts})
    _store.set_artifacts(normalized)
    return normalized


def _recover_artifacts(job: Job) -> ArtifactManifest | None:
    """Lazily read a manifest published after job completion (e.g. by finalize).

    The completion-time read in the orchestration backend happens once; runs
    finalized later would otherwise stay 409 forever. Any failure degrades to
    "not ready" rather than a 5xx.
    """
    reader = getattr(_backend, "artifact_reader", None)
    if reader is None or job.status != STATUS_COMPLETED:
        return None
    try:
        manifest = reader.read_manifest(job.id, job.id)
    except Exception:
        log.warning("lazy artifact manifest read failed for job %s", job.id, exc_info=True)
        return None
    if manifest is None:
        log.warning("lazy artifact manifest not found for job %s", job.id)
        return None
    _store.set_artifacts(manifest)
    return manifest


# Serve the built frontend if present (single-image deployment). Kept last so API routes win.
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
