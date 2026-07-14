"""Request/response and domain models for the SaaS job API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Job lifecycle states. The mock backend walks a job through these to a terminal state.
# Order matches the data plane's canonical run lifecycle (sim2policy runstate.py):
# training jobs render rollout media before evaluating the final policy.
STATUS_QUEUED = "queued"
STATUS_STARTING = "starting"
STATUS_TRAINING = "training"
STATUS_FINALIZING = "finalizing"
STATUS_RENDERING = "rendering"
STATUS_EVALUATING = "evaluating"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

TERMINAL_STATES = {STATUS_COMPLETED, STATUS_FAILED}

LIFECYCLE = [
    STATUS_QUEUED,
    STATUS_STARTING,
    STATUS_TRAINING,
    STATUS_FINALIZING,
    STATUS_RENDERING,
    STATUS_EVALUATING,
    STATUS_COMPLETED,
]


class JobRequest(BaseModel):
    """What a tenant submits: a preset shortcut, or environment + algorithm + params.

    Everything is validated against the server-side catalog; no free-form code or env.
    """

    gallery_example_id: str | None = Field(
        default=None, description="Stable server-owned gallery example ID."
    )
    gallery_profile_id: str | None = Field(
        default=None,
        description="Catalog-declared workload size for the selected example.",
    )
    preset: str | None = Field(
        default=None, description="Named shortcut, e.g. ant-demo."
    )
    environment: str | None = Field(default=None, description="Catalog environment id.")
    algorithm: str | None = Field(default=None, description="Catalog algorithm id.")
    params: dict[str, Any] = Field(
        default_factory=dict, description="Bounded overrides."
    )
    seed: int | None = Field(default=None, description="Legacy alias for params.seed.")

    model_config = ConfigDict(extra="forbid")


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
    phase: str | None = None
    failure_phase: str | None = None
    artifacts_status: str = "pending"
    job_kind: Literal["catalog", "custom-robot"] = "catalog"
    robot_id: str | None = None
    setup_id: str | None = None
    preparation_id: str | None = None
    preparation_fingerprint: str | None = None
    input_manifest_sha256: str | None = None
    gallery_example_id: str | None = None


class Artifact(BaseModel):
    id: str
    name: str
    kind: str = "file"
    content_type: str = "application/octet-stream"
    size_bytes: int | None = None
    sha256: str | None = None
    key: str


class ArtifactManifest(BaseModel):
    job_id: str
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    media: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)


# -- Bring Your Robot beta ---------------------------------------------------------------

RobotType = Literal["quadruped", "biped"]
TrainingReadiness = Literal[
    "ineligible",
    "not_prepared",
    "preparing",
    "ready",
    "preparation_failed",
]
PreparationState = Literal["queued", "preparing", "accepted", "failed"]


class FieldError(BaseModel):
    """Stable field-oriented diagnostic returned without echoing tenant content."""

    field: str
    message: str


class ValidationSummary(BaseModel):
    body_count: int
    joint_count: int
    actuator_count: int
    geom_count: int
    joint_names: list[str]
    actuator_names: list[str]


class RobotAsset(BaseModel):
    id: str
    # Used by the persistence layer, deliberately omitted from API serialization.
    tenant_id: str = Field(default="", exclude=True)
    name: str
    filename: str
    robot_type: RobotType
    digest: str
    validation: ValidationSummary
    validated_at: str
    readiness: Literal["validated"] = "validated"
    trainable: Literal[False] = False
    reason: Literal["custom-training-not-enabled"] = "custom-training-not-enabled"


class RobotSample(BaseModel):
    id: str
    name: str
    filename: str
    description: str
    robot_type: RobotType
    digest: str
    validation: ValidationSummary


class CatalogObjectInput(BaseModel):
    object_type: Literal["box", "ramp", "hurdle", "step"]
    x: float | None = None
    y: float | None = None
    z: float | None = None
    yaw_degrees: float | None = None
    width: float | None = None
    depth: float | None = None
    height: float | None = None

    model_config = ConfigDict(extra="forbid")


class CatalogObject(BaseModel):
    object_type: Literal["box", "ramp", "hurdle", "step"]
    x: float
    y: float
    z: float
    yaw_degrees: float
    width: float
    depth: float
    height: float
    source: Literal["preset", "custom"]


class ObjectParameter(BaseModel):
    name: str
    label: str
    default: float
    minimum: float
    maximum: float
    unit: str


class ObjectCatalogEntry(BaseModel):
    id: Literal["box", "ramp", "hurdle", "step"]
    label: str
    description: str
    parameters: list[ObjectParameter]


class TaskTemplate(BaseModel):
    id: Literal["stand-balance", "walk-forward", "recover-from-fall"]
    label: str
    description: str
    compatible_robot_types: list[RobotType]
    contract: dict[str, str]


class ScenePreset(BaseModel):
    id: Literal["flat-arena", "ramp-course", "hurdle-course", "step-course"]
    label: str
    description: str
    objects: list[CatalogObject]


class EnvironmentCatalog(BaseModel):
    task_templates: list[TaskTemplate]
    scene_presets: list[ScenePreset]
    object_types: list[ObjectCatalogEntry]
    max_objects: int = 6
    max_setups: int = 50
    arena_bounds: dict[str, list[float]]


class RobotSetupRequest(BaseModel):
    name: str
    robot_id: str
    task_template_id: str
    scene_preset_id: str
    objects: list[CatalogObjectInput] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class PreparationRequest(BaseModel):
    retry: bool = False

    model_config = ConfigDict(extra="forbid")


class CustomTrainingRequest(BaseModel):
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )

    model_config = ConfigDict(extra="forbid")


class PreparationAttempt(BaseModel):
    id: str
    tenant_id: str = Field(default="", exclude=True)
    setup_id: str
    robot_id: str
    fingerprint: str
    state: PreparationState
    phase: str
    created_at: str
    updated_at: str
    runtime_image_digest: str
    adapter_version: str
    reward_version: str
    profile_version: str
    retry_of: str | None = None
    failure_phase: str | None = None
    failure_reason: str | None = None
    report_sha256: str | None = None
    report_ready: bool = False
    can_retry: bool = False
    # Internal authorities are persisted but never serialized to tenant APIs.
    input_manifest_key: str | None = Field(default=None, exclude=True)
    input_manifest_sha256: str | None = Field(default=None, exclude=True)
    report_key: str | None = Field(default=None, exclude=True)
    nebius_job_id: str | None = Field(default=None, exclude=True)


class PreparationSummary(BaseModel):
    id: str
    fingerprint: str
    state: PreparationState
    phase: str
    created_at: str
    updated_at: str
    failure_phase: str | None = None
    failure_reason: str | None = None
    report_sha256: str | None = None
    report_ready: bool = False
    can_retry: bool = False


class RobotSetup(BaseModel):
    id: str
    tenant_id: str = Field(default="", exclude=True)
    name: str
    robot_id: str
    robot_name: str
    robot_type: RobotType
    task_template_id: str
    scene_preset_id: str
    objects: list[CatalogObject]
    digest: str
    created_at: str
    readiness: Literal["validated"] = "validated"
    trainable: bool = False
    reason: str = "custom-training-not-enabled"
    training_readiness: TrainingReadiness = "ineligible"
    can_prepare: bool = False
    can_start_training: bool = False
    current_preparation: PreparationSummary | None = None
