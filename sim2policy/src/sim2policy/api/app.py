"""FastAPI application for the hosted Sim2Policy demo API.

The app validates input against the preset allowlist, generates a safe run id,
persists run metadata, and triggers an orchestration backend. It never trains
itself and reads run status/artifacts from durable storage.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from sim2policy.api.models import HealthResponse, TrainRequest, TrainResponse
from sim2policy.api.orchestration import (
    MockBackend,
    OrchestrationBackend,
    OrchestrationError,
    build_backend,
)
from sim2policy.api.presets import PresetCatalog, PresetError, default_catalog_path
from sim2policy.config import ConfigError, StorageConfig, validate_run_id
from sim2policy.runstate import STATUS_QUEUED, RunStateStore


@dataclass
class Settings:
    backend_name: str = "mock"
    catalog_path: Path = default_catalog_path()
    runs_root: Path = Path("runs")
    demo_token: str | None = None
    submit_script: Path | None = None
    url_expiry: int = 3600
    storage: StorageConfig | None = None

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Settings:
        env = dict(environ if environ is not None else os.environ)
        bucket = env.get("SIM2POLICY_S3_BUCKET")
        storage = StorageConfig(
            mode="s3" if bucket else "local",
            bucket=bucket,
            prefix=env.get("SIM2POLICY_S3_PREFIX") or "sim2policy",
            endpoint_url=env.get("SIM2POLICY_S3_ENDPOINT"),
            region=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION"),
        )
        submit = env.get("SIM2POLICY_API_SUBMIT_SCRIPT")
        return cls(
            backend_name=env.get("SIM2POLICY_API_BACKEND", "mock"),
            catalog_path=Path(env["SIM2POLICY_API_PRESETS"])
            if env.get("SIM2POLICY_API_PRESETS")
            else default_catalog_path(),
            runs_root=Path(env.get("SIM2POLICY_API_RUNS_ROOT", "runs")),
            demo_token=env.get("SIM2POLICY_API_TOKEN") or None,
            submit_script=Path(submit) if submit else None,
            storage=storage,
        )


def _make_run_id(preset: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return validate_run_id(f"{preset}-{stamp}-{secrets.token_hex(3)}")


def create_app(
    settings: Settings | None = None,
    *,
    catalog: PresetCatalog | None = None,
    backend: OrchestrationBackend | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    catalog = catalog or PresetCatalog.load(settings.catalog_path)
    storage = settings.storage or StorageConfig()
    if backend is None:
        backend = (
            MockBackend(background=True)
            if settings.backend_name == "mock"
            else build_backend(
                settings.backend_name,
                submit_script=settings.submit_script,
            )
        )

    app = FastAPI(title="Sim2Policy Demo API", version="1.0")

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if not settings.demo_token:
            return
        expected = f"Bearer {settings.demo_token}"
        if not authorization or not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="invalid or missing demo token")

    def _state(run_id: str) -> RunStateStore:
        return RunStateStore(storage, run_id, settings.runs_root)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", backend=backend.name)

    @app.get("/training-options")
    def training_options(_: None = Depends(require_token)) -> dict[str, Any]:
        return {"presets": [preset.describe() for preset in catalog.list_enabled()]}

    @app.post("/train", response_model=TrainResponse, status_code=202)
    def train(request: TrainRequest, _: None = Depends(require_token)) -> TrainResponse:
        try:
            resolved = catalog.resolve(request.preset, request.safe_params())
        except PresetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        run_id = _make_run_id(request.preset)
        state = _state(run_id)
        state.write_request(
            {
                "run_id": run_id,
                "preset": request.preset,
                "safe_params": resolved.safe_params,
                "requested_at": datetime.now(UTC).isoformat(),
            }
        )
        state.init_status(preset=request.preset, status=STATUS_QUEUED)
        try:
            backend.launch(run_id, resolved, state)
        except OrchestrationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return TrainResponse(
            run_id=run_id, status=STATUS_QUEUED, status_url=f"/runs/{run_id}"
        )

    @app.get("/runs/{run_id}")
    def run_status(run_id: str, _: None = Depends(require_token)) -> dict[str, Any]:
        _validate_run_id(run_id)
        status = _state(run_id).read_status()
        if status is None:
            raise HTTPException(status_code=404, detail="run not found")
        return status.to_dict()

    @app.get("/runs/{run_id}/artifacts")
    def run_artifacts(run_id: str, _: None = Depends(require_token)) -> dict[str, Any]:
        _validate_run_id(run_id)
        state = _state(run_id)
        status = state.read_status()
        if status is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {
            "run_id": run_id,
            "status": status.status,
            "artifacts": state.artifact_urls(expires=settings.url_expiry),
        }

    return app


def _validate_run_id(run_id: str) -> None:
    try:
        validate_run_id(run_id)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail="invalid run id") from exc


def main() -> None:  # pragma: no cover - thin server entrypoint
    import uvicorn

    uvicorn.run(
        create_app(),
        host=os.getenv("SIM2POLICY_API_HOST", "127.0.0.1"),
        port=int(os.getenv("SIM2POLICY_API_PORT", "8000")),
    )


def __getattr__(name: str) -> Any:  # pragma: no cover - lazy ASGI export
    if name == "app":
        return create_app()
    raise AttributeError(name)
