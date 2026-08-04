"""Environment contract for the `nebius` orchestration backend.

All values are read once at startup and validated together, so a misconfigured pod
fails its readiness probe instead of failing on the first tenant request. The mock
backend needs none of this.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


class SettingsError(RuntimeError):
    """Raised at startup when the nebius backend is selected but misconfigured."""


# Required env vars and the settings field each one populates.
_REQUIRED = {
    "NEBIUS_PROJECT_ID": "project_id",
    "NEBIUS_SUBNET_ID": "subnet_id",
    "SIM2POLICY_MJX_JOB_IMAGE": "mjx_job_image",
    "NEBIUS_S3_SECRET_SELECTOR": "s3_secret_selector",
    "AWS_ACCESS_KEY_ID": "aws_access_key_id",
    "AWS_SECRET_ACCESS_KEY": "aws_secret_access_key",
    "AWS_ENDPOINT_URL_S3": "s3_endpoint_url",
    "AWS_DEFAULT_REGION": "s3_region",
    "SIM2POLICY_S3_BUCKET": "s3_bucket",
}

_OPTIONAL = {
    "NEBIUS_REGISTRY_SECRET": "registry_secret",
    "SIM2POLICY_JOB_IMAGE": "job_image",
}

_TRUE_VALUES = {"1", "true", "yes", "on"}
_IMMUTABLE_SB3_IMAGE_RE = re.compile(r"(?:@sha256:[0-9a-f]{64}|:sb3-[0-9a-f]{7,64})$")
_IMMUTABLE_MJX_IMAGE_RE = re.compile(r"(?:@sha256:[0-9a-f]{64}|:mjx-[0-9a-f]{7,64})$")


@dataclass(frozen=True)
class NebiusSettings:
    # Job submission
    project_id: str
    subnet_id: str
    mjx_job_image: str
    # MysteryBox selector resolving the artifact secret access key inside jobs
    # (the SDK equivalent of `nebius ai job create --env-secret`).
    s3_secret_selector: str
    # Artifact bucket access for the SaaS pod itself (non-secret key ID is paired
    # with the selector above; the secret key comes from the K8s Secret, never Git).
    aws_access_key_id: str
    aws_secret_access_key: str
    s3_endpoint_url: str
    s3_region: str
    s3_bucket: str
    # Optional
    registry_secret: str | None = None
    job_image: str | None = (
        None  # legacy SB3 image; no longer required by the GPU-only catalog
    )

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> NebiusSettings:
        env = os.environ if env is None else env
        missing = [name for name in _REQUIRED if not env.get(name)]
        if missing:
            raise SettingsError(
                "nebius orchestration backend selected but required environment "
                f"variables are missing: {', '.join(sorted(missing))}"
            )
        values = {field: env[name] for name, field in _REQUIRED.items()}
        values.update(
            {field: env.get(name) or None for name, field in _OPTIONAL.items()}
        )
        return cls(**values)


@dataclass(frozen=True)
class CustomTrainingSettings:
    """Disabled-by-default control-plane contract for uploaded-robot execution."""

    enabled: bool
    runtime_image: str
    max_active_preparations_per_tenant: int
    max_active_training_jobs_per_tenant: int
    max_daily_starts_per_tenant: int
    preparation_finalize_attempts: int
    feature_revision: str

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        orchestration_backend: str = "mock",
    ) -> CustomTrainingSettings:
        env = os.environ if env is None else env
        enabled = (
            env.get("CUSTOM_ROBOT_TRAINING_ENABLED", "false").strip().lower()
            in _TRUE_VALUES
        )
        runtime_image = env.get("CUSTOM_ROBOT_SB3_IMAGE", "").strip()
        if not runtime_image and orchestration_backend == "mock":
            runtime_image = "local-custom-robot-sb3-v1"
        if enabled and orchestration_backend == "nebius":
            if not runtime_image:
                raise SettingsError(
                    "custom robot training is enabled but CUSTOM_ROBOT_SB3_IMAGE is missing"
                )
            if not _IMMUTABLE_SB3_IMAGE_RE.search(runtime_image):
                raise SettingsError(
                    "CUSTOM_ROBOT_SB3_IMAGE must use an immutable sb3-<git-sha> tag or digest"
                )

        def positive_int(name: str, default: int, *, maximum: int) -> int:
            raw = env.get(name, str(default))
            try:
                value = int(raw)
            except ValueError as exc:
                raise SettingsError(f"{name} must be an integer") from exc
            if not 1 <= value <= maximum:
                raise SettingsError(f"{name} must be between 1 and {maximum}")
            return value

        return cls(
            enabled=enabled,
            runtime_image=runtime_image or "custom-robot-training-disabled",
            max_active_preparations_per_tenant=positive_int(
                "CUSTOM_ROBOT_MAX_ACTIVE_PREPARATIONS", 1, maximum=10
            ),
            max_active_training_jobs_per_tenant=positive_int(
                "CUSTOM_ROBOT_MAX_ACTIVE_TRAINING_JOBS", 1, maximum=10
            ),
            max_daily_starts_per_tenant=positive_int(
                "CUSTOM_ROBOT_MAX_DAILY_STARTS", 8, maximum=100
            ),
            preparation_finalize_attempts=positive_int(
                "CUSTOM_ROBOT_PREPARATION_FINALIZE_ATTEMPTS", 60, maximum=720
            ),
            feature_revision=env.get(
                "CUSTOM_ROBOT_FEATURE_REVISION", "custom-robot-v1"
            ).strip()
            or "custom-robot-v1",
        )


@dataclass(frozen=True)
class ShowcaseSettings:
    """Operator kill-switch for the public read-only showcase.

    Enabled by default, unlike the trainable gallery switch it replaces. That switch
    was disabled-first because every card could spend GPU budget; this one only
    reveals evidence from runs already paid for, and it is the application's public
    landing experience, so defaulting it off would serve visitors an empty page.

    It carries no immutable-runtime-image requirement any more: those gated whether
    a card was safe to *submit*, and nothing in the showcase is submittable. What a
    showcase entry may reveal is gated per entry by its pinned run's evidence.
    """

    enabled: bool

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        orchestration_backend: str = "mock",
    ) -> ShowcaseSettings:
        env = os.environ if env is None else env
        # `SAAS_GALLERY_ENABLED` is deliberately NOT honoured here. It meant "do not
        # let tenants spend GPU budget on gallery training" — a safety choice that
        # must not silently translate into "hide the public evidence page", which is
        # what reusing it would do to any deployment that set it to false.
        raw = env.get("SAAS_SHOWCASE_ENABLED", "true")
        return cls(enabled=raw.strip().lower() in _TRUE_VALUES)
