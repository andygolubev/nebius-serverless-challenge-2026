"""Request/response and domain models for the SaaS job API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Job lifecycle states. The mock backend walks a job through these to a terminal state.
# Order matches the data plane's canonical run lifecycle (sim2policy runstate.py):
# training jobs render rollout media before evaluating the final policy.
STATUS_QUEUED = "queued"
STATUS_STARTING = "starting"
STATUS_TRAINING = "training"
STATUS_RENDERING = "rendering"
STATUS_EVALUATING = "evaluating"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

TERMINAL_STATES = {STATUS_COMPLETED, STATUS_FAILED}

LIFECYCLE = [
    STATUS_QUEUED,
    STATUS_STARTING,
    STATUS_TRAINING,
    STATUS_RENDERING,
    STATUS_EVALUATING,
    STATUS_COMPLETED,
]


class JobRequest(BaseModel):
    """What a tenant submits: a preset shortcut, or environment + algorithm + params.

    Everything is validated against the server-side catalog; no free-form code or env.
    """

    preset: str | None = Field(default=None, description="Named shortcut, e.g. ant-demo.")
    environment: str | None = Field(default=None, description="Catalog environment id.")
    algorithm: str | None = Field(default=None, description="Catalog algorithm id.")
    params: dict[str, Any] = Field(default_factory=dict, description="Bounded overrides.")
    seed: int | None = Field(default=None, description="Legacy alias for params.seed.")


class AuthRequest(BaseModel):
    email: str


class VerifyRequest(BaseModel):
    email: str
    code: str


class Job(BaseModel):
    id: str
    tenant_id: str
    preset: str | None = None
    environment: str
    algorithm: str
    resolved_config: dict[str, Any]
    status: str
    created_at: str
    updated_at: str
    # Nebius Serverless AI job resource ID (`aijob-*`); set by the nebius backend
    # at submission time so polling/cancellation can address the remote job.
    nebius_job_id: str | None = None
    # Short, sanitized failure summary surfaced to the tenant. Never raw errors.
    error: str | None = None


class ArtifactManifest(BaseModel):
    job_id: str
    status: str
    metrics: dict[str, Any] = {}
    media: list[str] = []
