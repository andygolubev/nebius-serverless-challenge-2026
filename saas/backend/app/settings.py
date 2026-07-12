"""Environment contract for the `nebius` orchestration backend.

All values are read once at startup and validated together, so a misconfigured pod
fails its readiness probe instead of failing on the first tenant request. The mock
backend needs none of this.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class SettingsError(RuntimeError):
    """Raised at startup when the nebius backend is selected but misconfigured."""


# Required env vars and the settings field each one populates.
_REQUIRED = {
    "NEBIUS_PROJECT_ID": "project_id",
    "NEBIUS_SUBNET_ID": "subnet_id",
    "SIM2POLICY_JOB_IMAGE": "job_image",
    "SIM2POLICY_MJX_JOB_IMAGE": "mjx_job_image",
    "NEBIUS_S3_SECRET_SELECTOR": "s3_secret_selector",
    "AWS_ACCESS_KEY_ID": "aws_access_key_id",
    "AWS_SECRET_ACCESS_KEY": "aws_secret_access_key",
    "AWS_ENDPOINT_URL_S3": "s3_endpoint_url",
    "AWS_DEFAULT_REGION": "s3_region",
    "SIM2POLICY_S3_BUCKET": "s3_bucket",
}

_OPTIONAL = {"NEBIUS_REGISTRY_SECRET": "registry_secret"}


@dataclass(frozen=True)
class NebiusSettings:
    # Job submission
    project_id: str
    subnet_id: str
    job_image: str  # SB3 runtime image; specs with image_key="mjx" use mjx_job_image
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
        values.update({field: env.get(name) or None for name, field in _OPTIONAL.items()})
        return cls(**values)
