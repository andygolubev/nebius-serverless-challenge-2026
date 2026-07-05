"""Request/response and domain models for the SaaS job API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Job lifecycle states. The mock backend walks a job through these to a terminal state.
STATUS_QUEUED = "queued"
STATUS_STARTING = "starting"
STATUS_TRAINING = "training"
STATUS_EVALUATING = "evaluating"
STATUS_RENDERING = "rendering"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

TERMINAL_STATES = {STATUS_COMPLETED, STATUS_FAILED}

LIFECYCLE = [
    STATUS_QUEUED,
    STATUS_STARTING,
    STATUS_TRAINING,
    STATUS_EVALUATING,
    STATUS_RENDERING,
    STATUS_COMPLETED,
]


class JobRequest(BaseModel):
    """What a tenant submits. Preset-driven, mirroring the demo API contract."""

    preset: str = Field(..., description="Allowlisted training preset, e.g. ant-demo.")
    seed: int | None = Field(default=None, description="Optional safe override.")


class Job(BaseModel):
    id: str
    tenant_id: str
    preset: str
    seed: int | None
    status: str
    created_at: str
    updated_at: str


class ArtifactManifest(BaseModel):
    job_id: str
    status: str
    metrics: dict[str, Any] = {}
    media: list[str] = []
