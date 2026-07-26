"""FastAPI entrypoint for the SaaS control-plane app.

Serves the auth + job API and (when built) the static frontend. Identity comes from a
bearer session token issued after email one-time-code verification; every job and
artifact is scoped to the session's tenant (the verified email).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import catalog, environment_catalog, showcase
from .auth import (
    AuthService,
    RateLimited,
    is_valid_email,
    normalize_email,
)
from .custom_training import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    build_input_documents,
    canonical_json,
    eligibility,
    preparation_fingerprint,
    project_setup_readiness,
    resolved_custom_job,
    sha256_bytes,
)
from .email_sender import EmailDeliveryError, build_email_sender
from .models import (
    STATUS_COMPLETED,
    STATUS_QUEUED,
    Artifact,
    ArtifactManifest,
    AuthRequest,
    Job,
    JobRequest,
    CustomTrainingRequest,
    PreparationAttempt,
    PreparationRequest,
    RobotAsset,
    RobotSample,
    RobotSetup,
    RobotSetupRequest,
    VerifyRequest,
)
from .orchestration import build_backend
from .robot_validation import MAX_ROBOT_BYTES, RobotValidationError, validate_mjcf
from .settings import CustomTrainingSettings, ShowcaseSettings
from .store import (
    AuthStore,
    CustomTrainingStore,
    JobStore,
    QuotaExceeded,
    RobotStore,
    Session,
)
from .db import resolve_path

app = FastAPI(title="Sim2Policy SaaS", version="0.2.0")
log = logging.getLogger(__name__)
# Durable state lives in SQLite at SAAS_DB_PATH (a PVC in the cluster); defaults to a
# local file for development.
_db_path = resolve_path()
_store = JobStore(_db_path)
_robot_store = RobotStore(_db_path)
_custom_store = CustomTrainingStore(_db_path)
_backend_name = os.environ.get("SAAS_ORCHESTRATION_BACKEND", "mock")
_backend = build_backend(_backend_name)
_custom_settings = getattr(
    _backend,
    "custom_settings",
    CustomTrainingSettings.from_env(orchestration_backend=_backend_name),
)
_showcase_settings = ShowcaseSettings.from_env(orchestration_backend=_backend_name)
_showcase = showcase.ShowcaseService(_store, _backend, _showcase_settings)
_showcase_limiter = showcase.RateLimiter()
_auth = AuthService(
    AuthStore(_db_path),
    build_email_sender(os.environ.get("SAAS_EMAIL_BACKEND", "mock")),
)


@app.on_event("startup")
def resume_jobs() -> None:
    # Samples are part of the public upload contract. Refuse to start if packaging or
    # validation drift made either example unusable.
    _load_robot_samples()
    # Pinned showcase runs are checked once here so an unsafe literal is rejected
    # before it can be served, without failing readiness over one bad entry.
    catalog.validate_showcase_runs()
    resume = getattr(_backend, "resume", None)
    if resume is not None:
        resume(_store)
    resume_preparations = getattr(_backend, "resume_preparations", None)
    if resume_preparations is not None:
        resume_preparations(_custom_store)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _field_error(field: str, message: str, *, status_code: int = 422) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"field": field, "message": message}
    )


def _project_setup(setup: RobotSetup) -> RobotSetup:
    robot = _robot_store.get_robot(setup.tenant_id, setup.robot_id)
    if robot is None:
        return setup.model_copy(
            update={
                "trainable": False,
                "reason": "source-robot-unavailable",
                "training_readiness": "ineligible",
                "can_prepare": False,
                "can_start_training": False,
                "current_preparation": None,
            }
        )
    latest = _custom_store.latest_preparation(setup.tenant_id, setup.id)
    return project_setup_readiness(
        setup,
        robot,
        latest,
        enabled=_custom_settings.enabled,
        runtime_image_digest=_custom_settings.runtime_image,
    )


_SAMPLE_DEFINITIONS = {
    "sample-quadruped": (
        "Sample quadruped",
        "sample-quadruped.xml",
        "quadruped",
        "Eight-actuator primitive quadruped for upload and setup validation.",
    ),
    "sample-biped": (
        "Sample biped",
        "sample-biped.xml",
        "biped",
        "Seven-actuator primitive biped for upload and setup validation.",
    ),
}


def _samples_dir() -> Path:
    configured = os.environ.get("SAAS_ROBOT_SAMPLES_DIR")
    candidates = [
        Path(configured) if configured else None,
        Path(__file__).resolve().parent.parent / "samples" / "robots",
        Path(__file__).resolve().parent.parent.parent / "samples" / "robots",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate
    raise RuntimeError("packaged robot samples directory is missing")


def _load_robot_samples() -> dict[str, tuple[RobotSample, bytes]]:
    loaded: dict[str, tuple[RobotSample, bytes]] = {}
    directory = _samples_dir()
    for sample_id, (
        name,
        filename,
        robot_type,
        description,
    ) in _SAMPLE_DEFINITIONS.items():
        raw = (directory / filename).read_bytes()
        _, digest, summary = validate_mjcf(raw)
        loaded[sample_id] = (
            RobotSample(
                id=sample_id,
                name=name,
                filename=filename,
                description=description,
                robot_type=robot_type,
                digest=digest,
                validation=summary,
            ),
            raw,
        )
    return loaded


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
        "custom_robot_training": "enabled" if _custom_settings.enabled else "disabled",
        "showcase": "enabled" if _showcase_settings.enabled else "disabled",
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
        raise HTTPException(
            status_code=429, detail="too many code requests; try again later"
        )
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


# -- Bring Your Robot beta --


@app.get("/robot-samples")
def list_robot_samples(
    session: Session = Depends(require_session),
) -> list[RobotSample]:
    del session
    return [sample for sample, _ in _load_robot_samples().values()]


@app.get("/robot-samples/{sample_id}")
def download_robot_sample(
    sample_id: str, session: Session = Depends(require_session)
) -> Response:
    del session
    entry = _load_robot_samples().get(sample_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="sample not found")
    sample, raw = entry
    return Response(
        content=raw,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{sample.filename}"'},
    )


@app.post("/robots", status_code=201)
async def upload_robot(
    name: str = Form(""),
    robot_type: str = Form(""),
    file: UploadFile | None = File(None),
    session: Session = Depends(require_session),
) -> RobotAsset:
    normalized_name = name.strip()
    if not normalized_name or len(normalized_name) > 80:
        raise _field_error("name", "name must contain 1 to 80 characters")
    if robot_type not in {"quadruped", "biped"}:
        raise _field_error("robot_type", "choose quadruped or biped")
    if file is None:
        raise _field_error("file", "upload one .xml file with a safe filename")
    filename = file.filename or ""
    if (
        not filename
        or Path(filename).name != filename
        or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._ -]{0,115}\.xml", filename, re.IGNORECASE
        )
    ):
        raise _field_error("file", "upload one .xml file with a safe filename")
    content = bytearray()
    try:
        while chunk := await file.read(64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_ROBOT_BYTES:
                raise _field_error("file", "MJCF file must be at most 1 MiB")
    finally:
        await file.close()
    try:
        xml_content, digest, summary = validate_mjcf(bytes(content))
    except RobotValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    robot = RobotAsset(
        id=uuid.uuid4().hex,
        tenant_id=session.email,
        name=normalized_name,
        filename=filename,
        robot_type=robot_type,
        digest=digest,
        validation=summary,
        validated_at=_now(),
    )
    try:
        stored, _ = _robot_store.create_robot(robot, xml_content)
    except QuotaExceeded as exc:
        raise _field_error(
            exc.field, f"tenant limit is {exc.limit} active robot versions"
        ) from exc
    return stored


@app.get("/robots")
def list_robots(session: Session = Depends(require_session)) -> list[RobotAsset]:
    return _robot_store.list_robots(session.email)


@app.get("/robots/{robot_id}")
def get_robot(robot_id: str, session: Session = Depends(require_session)) -> RobotAsset:
    robot = _robot_store.get_robot(session.email, robot_id)
    if robot is None:
        raise HTTPException(status_code=404, detail="robot not found")
    return robot


@app.get("/robots/{robot_id}/content")
def get_robot_content(
    robot_id: str, session: Session = Depends(require_session)
) -> Response:
    entry = _robot_store.get_robot_content(session.email, robot_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="robot not found")
    robot, content = entry
    return Response(
        content=content.encode("utf-8"),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{robot.filename}"'},
    )


@app.delete("/robots/{robot_id}", status_code=204)
def delete_robot(
    robot_id: str, session: Session = Depends(require_session)
) -> Response:
    if not _robot_store.delete_robot(session.email, robot_id):
        raise HTTPException(status_code=404, detail="robot not found")
    return Response(status_code=204)


@app.get("/environment-catalog")
def get_environment_catalog(session: Session = Depends(require_session)) -> dict:
    del session
    return environment_catalog.serialize().model_dump(mode="json")


@app.post("/robot-setups", status_code=201)
def create_robot_setup(
    request: RobotSetupRequest,
    session: Session = Depends(require_session),
) -> RobotSetup:
    name = request.name.strip()
    if not name or len(name) > 80:
        raise _field_error("name", "name must contain 1 to 80 characters")
    robot = _robot_store.get_robot(session.email, request.robot_id)
    if robot is None:
        raise HTTPException(status_code=404, detail="robot not found")
    try:
        objects, digest = environment_catalog.normalize_setup(
            robot.id,
            robot.robot_type,
            request.task_template_id,
            request.scene_preset_id,
            request.objects,
        )
    except environment_catalog.BuilderValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    setup = RobotSetup(
        id=uuid.uuid4().hex,
        tenant_id=session.email,
        name=name,
        robot_id=robot.id,
        robot_name=robot.name,
        robot_type=robot.robot_type,
        task_template_id=request.task_template_id,
        scene_preset_id=request.scene_preset_id,
        objects=objects,
        digest=digest,
        created_at=_now(),
    )
    try:
        stored, _ = _robot_store.create_setup(setup)
    except QuotaExceeded as exc:
        raise _field_error(
            exc.field, f"tenant limit is {exc.limit} active environment setups"
        ) from exc
    return _project_setup(stored)


@app.get("/robot-setups")
def list_robot_setups(session: Session = Depends(require_session)) -> list[RobotSetup]:
    return [_project_setup(setup) for setup in _robot_store.list_setups(session.email)]


@app.get("/robot-setups/{setup_id}")
def get_robot_setup(
    setup_id: str, session: Session = Depends(require_session)
) -> RobotSetup:
    setup = _robot_store.get_setup(session.email, setup_id)
    if setup is None:
        raise HTTPException(status_code=404, detail="setup not found")
    return _project_setup(setup)


@app.delete("/robot-setups/{setup_id}", status_code=204)
def delete_robot_setup(
    setup_id: str, session: Session = Depends(require_session)
) -> Response:
    if not _robot_store.delete_setup(session.email, setup_id):
        raise HTTPException(status_code=404, detail="setup not found")
    return Response(status_code=204)


@app.post("/robot-setups/{setup_id}/preparations", status_code=201)
def prepare_robot_setup(
    setup_id: str,
    request: PreparationRequest,
    session: Session = Depends(require_session),
) -> PreparationAttempt:
    setup = _robot_store.get_setup(session.email, setup_id)
    if setup is None:
        raise HTTPException(status_code=404, detail="setup not found")
    robot_entry = _robot_store.get_robot_content(session.email, setup.robot_id)
    if robot_entry is None:
        raise HTTPException(status_code=409, detail="source robot is unavailable")
    robot, robot_xml = robot_entry
    allowed = eligibility(setup, enabled=_custom_settings.enabled)
    if not allowed.eligible:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": allowed.reason,
                "message": "setup is not eligible for preparation",
            },
        )
    fingerprint = preparation_fingerprint(robot, setup, _custom_settings.runtime_image)
    previous = _custom_store.latest_preparation(session.email, setup.id)
    now = _now()
    attempt = PreparationAttempt(
        id=uuid.uuid4().hex,
        tenant_id=session.email,
        setup_id=setup.id,
        robot_id=robot.id,
        fingerprint=fingerprint,
        state="queued",
        phase="queued",
        created_at=now,
        updated_at=now,
        runtime_image_digest=_custom_settings.runtime_image,
        adapter_version=ADAPTER_VERSION,
        reward_version=REWARD_VERSION,
        profile_version=PREPARATION_PROFILE_VERSION,
        retry_of=(previous.id if request.retry and previous is not None else None),
    )
    try:
        attempt, created = _custom_store.reserve_preparation(
            attempt,
            max_active_per_tenant=_custom_settings.max_active_preparations_per_tenant,
            retry=request.retry,
        )
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "reason": exc.field,
                "message": "preparation capacity is currently in use",
            },
            headers={"Retry-After": "30"},
        ) from exc
    if not created:
        return attempt
    robot_bytes, setup_bytes, manifest = build_input_documents(
        preparation_id=attempt.id,
        robot=robot,
        robot_xml=robot_xml,
        setup=setup,
        runtime_image_digest=_custom_settings.runtime_image,
    )
    manifest_bytes = canonical_json(manifest)
    attempt = attempt.model_copy(
        update={
            "input_manifest_key": (
                f"sim2policy/preparations/{attempt.id}/inputs/input-manifest.json"
            ),
            "input_manifest_sha256": sha256_bytes(manifest_bytes),
            "report_key": (
                f"sim2policy/preparations/{attempt.id}/report/preparation.json"
            ),
        }
    )
    _custom_store.put_preparation(attempt)
    storage = getattr(_backend, "custom_storage", None)
    if storage is not None:
        try:
            storage.publish_preparation_inputs(
                attempt.id,
                robot=robot_bytes,
                setup=setup_bytes,
                manifest=manifest_bytes,
            )
        except Exception:
            failed = attempt.model_copy(
                update={
                    "state": "failed",
                    "phase": "input-publication",
                    "failure_phase": "input-publication",
                    "failure_reason": "input-publication-failed",
                    "can_retry": True,
                    "updated_at": _now(),
                }
            )
            _custom_store.put_preparation(failed)
            raise HTTPException(
                status_code=503, detail="preparation input publication failed"
            )
    _backend.launch_preparation(attempt, _custom_store)
    return attempt


@app.get("/robot-setups/{setup_id}/preparations/latest")
def latest_robot_setup_preparation(
    setup_id: str,
    session: Session = Depends(require_session),
) -> PreparationAttempt:
    setup = _robot_store.get_setup_history(session.email, setup_id)
    if setup is None:
        raise HTTPException(status_code=404, detail="setup not found")
    attempt = _custom_store.latest_preparation(session.email, setup.id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="preparation not found")
    return attempt


@app.post("/robot-setups/{setup_id}/training-jobs", status_code=201)
def start_robot_setup_training(
    setup_id: str,
    request: CustomTrainingRequest,
    session: Session = Depends(require_session),
) -> Job:
    setup = _robot_store.get_setup(session.email, setup_id)
    if setup is None:
        raise HTTPException(status_code=404, detail="setup not found")
    robot_entry = _robot_store.get_robot_content(session.email, setup.robot_id)
    if robot_entry is None:
        raise HTTPException(status_code=409, detail="source robot is unavailable")
    robot, robot_xml = robot_entry
    attempt = _custom_store.latest_preparation(session.email, setup.id)
    current_fingerprint = preparation_fingerprint(
        robot, setup, _custom_settings.runtime_image
    )
    if (
        not _custom_settings.enabled
        or attempt is None
        or attempt.state != "accepted"
        or attempt.fingerprint != current_fingerprint
        or not attempt.report_ready
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "accepted-preparation-required",
                "message": "prepare the current setup before starting training",
            },
        )
    robot_bytes, setup_bytes, manifest = build_input_documents(
        preparation_id=attempt.id,
        robot=robot,
        robot_xml=robot_xml,
        setup=setup,
        runtime_image_digest=_custom_settings.runtime_image,
    )
    manifest_bytes = canonical_json(manifest)
    now = _now()
    job = Job(
        id=uuid.uuid4().hex,
        tenant_id=session.email,
        preset=None,
        environment=f"uploaded-{robot.robot_type}",
        algorithm="ppo-sb3",
        resolved_config=resolved_custom_job(robot, setup, attempt),
        status=STATUS_QUEUED,
        created_at=now,
        updated_at=now,
        job_kind="custom-robot",
        robot_id=robot.id,
        setup_id=setup.id,
        preparation_id=attempt.id,
        preparation_fingerprint=attempt.fingerprint,
        input_manifest_sha256=sha256_bytes(manifest_bytes),
    )
    try:
        job, created = _custom_store.reserve_training_job(
            job,
            setup_id=setup.id,
            idempotency_key=request.idempotency_key,
            max_active_per_tenant=_custom_settings.max_active_training_jobs_per_tenant,
            max_daily_starts=_custom_settings.max_daily_starts_per_tenant,
        )
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"reason": exc.field, "message": "custom training quota reached"},
            headers={"Retry-After": "60"},
        ) from exc
    if not created:
        return job
    storage = getattr(_backend, "custom_storage", None)
    if storage is not None:
        try:
            storage.snapshot_training_inputs(
                job.id,
                robot=robot_bytes,
                setup=setup_bytes,
                manifest=manifest_bytes,
            )
        except Exception:
            failed = job.model_copy(
                update={
                    "status": "failed",
                    "phase": "input-publication",
                    "failure_phase": "input-publication",
                    "error": "training input snapshot failed",
                    "updated_at": _now(),
                }
            )
            _store.put(failed)
            raise HTTPException(
                status_code=503, detail="training input snapshot failed"
            )
    _backend.launch(job, _store)
    return job


# -- public showcase --
#
# These handlers take no session parameter at all — not an optional one. A route with
# an optional session is a route where someone can later widen access with `if
# session:`. Access is decided solely by the pinned-run allowlist, so a request
# bearing a valid token receives a byte-identical response. Nothing here creates,
# mutates, or launches anything.


def _public_guard(request: Request) -> None:
    """Bound anonymous traffic per client address."""
    client = request.client.host if request.client else "unknown"
    if not _showcase_limiter.allow(client):
        raise HTTPException(status_code=429, detail="too many requests; slow down")


@app.get("/showcase")
def list_showcase(request: Request) -> dict:
    _public_guard(request)
    try:
        return {"examples": _showcase.entries()}
    except Exception:
        # Never leak a storage error to an anonymous caller, and never 5xx the
        # landing page: an unreadable entry is simply not published.
        log.warning("showcase catalog read failed", exc_info=True)
        return {"examples": []}


@app.get("/showcase/{example_id}")
def get_showcase_example(example_id: str, request: Request) -> dict:
    _public_guard(request)
    try:
        detail = _showcase.detail(example_id)
    except Exception:
        log.warning("showcase detail read failed", exc_info=True)
        raise HTTPException(status_code=503, detail="showcase is temporarily unavailable")
    if detail is None:
        # Unknown, hidden, and gate-failing entries are indistinguishable.
        raise HTTPException(status_code=404, detail="example not found")
    return detail


@app.get("/showcase/{example_id}/artifacts/{artifact_id}")
def access_showcase_artifact(
    example_id: str,
    artifact_id: str,
    request: Request,
    download: bool = False,
):
    _public_guard(request)
    try:
        artifact = _showcase.artifact(example_id, artifact_id)
        url = _showcase.presigned(artifact, download=download) if artifact else None
    except Exception:
        log.warning("showcase artifact access failed", exc_info=True)
        raise HTTPException(status_code=503, detail="artifact is temporarily unavailable")
    if artifact is None or url is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    # Redirects to a short-lived, read-only URL for exactly one validated object.
    # Range requests are served by object storage, so seeking works without
    # downloading the whole file.
    return RedirectResponse(url, status_code=307)


@app.get("/training-options")
def training_options(request: Request) -> dict:
    """Showcase display metadata. Retained for existing clients; prefer /showcase."""
    _public_guard(request)
    try:
        return showcase.serialize_options(_showcase)
    except Exception:
        log.warning("showcase options read failed", exc_info=True)
        return {"showcase_enabled": _showcase.enabled, "examples": []}


# -- jobs --


@app.post("/jobs", status_code=410)
def submit_job(req: JobRequest, session: Session = Depends(require_session)) -> dict:
    """Refuse every catalog submission; training starts from an owned robot setup.

    The verified examples are a read-only showcase of runs that were already
    performed, so there is nothing here to submit. `POST /jobs` is retained only to
    answer an old client honestly rather than 404-ing it. No branch of this handler
    can create a SaaS job record or a remote resource.
    """
    raise HTTPException(
        status_code=410,
        detail={
            "field": "gallery_example_id",
            "message": (
                "Verified examples are a read-only showcase and cannot be trained. "
                "To train, upload a robot, save a setup, prepare it, and start it with "
                "POST /robot-setups/{setup_id}/training-jobs."
            ),
        },
    )


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
            artifact["url"] = reader.presigned_url(
                stored.key, content_type=stored.content_type
            )
            artifact["download_url"] = reader.presigned_url(
                stored.key,
                content_type=stored.content_type,
                download_name=stored.key.rsplit("/", 1)[-1],
            )
        else:
            artifact["url"] = f"/jobs/{job_id}/artifacts/{artifact['id']}"
            artifact["download_url"] = (
                f"/jobs/{job_id}/artifacts/{artifact['id']}?download=true"
            )
    return data


@app.get("/jobs/{job_id}/artifacts/{artifact_id}")
def access_artifact(
    job_id: str,
    artifact_id: str,
    download: bool = False,
    session: Session = Depends(require_session),
):
    job = _store.get(session.email, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    manifest = _store.get_artifacts(job_id) or _recover_artifacts(job)
    if manifest is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    manifest = _normalize_legacy_manifest(manifest)
    artifact = next(
        (item for item in manifest.artifacts if item.id == artifact_id), None
    )
    reader = getattr(_backend, "artifact_reader", None)
    if artifact is None or reader is None or not hasattr(reader, "presigned_url"):
        raise HTTPException(status_code=404, detail="artifact not found")
    filename = artifact.key.rsplit("/", 1)[-1] if download else None
    return RedirectResponse(
        reader.presigned_url(
            artifact.key, content_type=artifact.content_type, download_name=filename
        ),
        status_code=307,
    )


def _normalize_legacy_manifest(manifest: ArtifactManifest) -> ArtifactManifest:
    if manifest.artifacts or not manifest.media:
        return manifest
    artifacts = []
    for index, key in enumerate(manifest.media):
        if not isinstance(key, str) or ".." in key.split("/"):
            continue
        filename = key.rsplit("/", 1)[-1]
        stem = filename.rsplit(".", 1)[0]
        artifacts.append(
            Artifact(
                id=f"legacy-{index}-{stem}",
                name=stem.replace("_", " ").replace("-", " ").title(),
                kind="video" if filename.endswith(".mp4") else "file",
                content_type="video/mp4"
                if filename.endswith(".mp4")
                else "application/octet-stream",
                key=key,
            )
        )
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
        log.warning(
            "lazy artifact manifest read failed for job %s", job.id, exc_info=True
        )
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
