"""Thin wrapper around the official Nebius Python SDK (`pip install nebius`).

Everything SDK-specific lives here: `NebiusBackend` talks to the `JobsClient`
protocol, so unit tests inject a fake and never import the SDK. The submission
shape mirrors `sim2policy/jobs/submit.sh` (the verified CLI reference): image,
`python -m <module> ...` container command, platform/preset, timeout, subnet,
no restarts, registry secret, S3 access key as plain env and the secret access
key only as a MysteryBox reference (`--env-secret` equivalent).

Field and enum names below were verified against nebius 0.3.92:
`CreateJobRequest(metadata=ResourceMetadata(parent_id, name), spec=JobSpec(...))`,
`JobSpec(EnvironmentVariable(name, value | mysterybox_secret), timeout=timedelta,
restart_attempts, registry_credentials)`, and `JobStatus.State` values
PROVISIONING/STARTING/RUNNING/CANCELLING/DELETING/COMPLETED/FAILED/CANCELLED/ERROR.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol


@dataclass(frozen=True)
class JobSubmission:
    """SDK-agnostic description of one Serverless AI job."""

    name: str
    image: str
    command: str  # container command, e.g. "python"
    args: list[str]
    platform: str
    preset: str
    timeout_seconds: int
    subnet_id: str
    parent_id: str
    registry_secret: str | None = None  # MysteryBox secret version for pulls
    # Boot disk for the job VM; the API rejects specs without an explicit disk
    # (`spec.disk: value is required`). The CLI default of 250Gi exceeds the
    # project's SSD quota headroom and leaves jobs stuck in PROVISIONING; 100Gi
    # is verified to provision and fits the training image plus run artifacts.
    disk_gib: int = 100
    env: dict[str, str] = field(default_factory=dict)
    # name -> MysteryBox selector; the value never appears in the job spec.
    env_secrets: dict[str, str] = field(default_factory=dict)


class JobsClient(Protocol):
    def create_job(self, submission: JobSubmission) -> str:
        """Submit the job; return the `aijob-*` resource ID."""
        ...

    def get_job_state(self, job_id: str) -> str:
        """Return the raw Nebius job state name for a previously created job."""
        ...


def split_secret_selector(selector: str) -> tuple[str, str | None]:
    """Split a MysteryBox selector into (secret_id, version_id).

    The infra output (`artifact_secret_selector`) is a secret reference ID; a
    `secret/version` form selects a specific version, matching the CLI's
    `--env-secret` selector semantics.
    """
    secret_id, _, version_id = selector.partition("/")
    return secret_id, version_id or None


class SdkJobsClient:
    """Real client backed by `nebius.api.nebius.ai.v1.JobServiceClient`.

    Imports the SDK lazily so the mock orchestration backend works in
    environments without the `nebius` package installed.
    """

    def __init__(self, token_file: str = "/var/run/secrets/nebius-metadata/token") -> None:
        from nebius.sdk import SDK
        from nebius.aio.token.file import Bearer as FileBearer

        # Nebius Compute continuously refreshes the VM service-account token at
        # /mnt/cloud-metadata/token through an atomically replaced `..data`
        # symlink. k3s mounts the whole metadata directory read-only so the
        # container follows each replacement; mounting only the token file
        # pins the old inode and eventually yields UNAUTHENTICATED.
        # FileBearer re-reads rotations without a long-lived private key.
        self._sdk = SDK(credentials=FileBearer(token_file))

    def _service(self):
        from nebius.api.nebius.ai.v1 import JobServiceClient

        return JobServiceClient(self._sdk)

    def create_job(self, submission: JobSubmission) -> str:
        from nebius.api.nebius.ai.v1 import CreateJobRequest, JobSpec
        from nebius.api.nebius.common.v1 import ResourceMetadata
        from nebius.api.nebius.compute.v1 import DiskSpec as ComputeDiskSpec

        env_vars = [
            JobSpec.EnvironmentVariable(name=name, value=value)
            for name, value in submission.env.items()
        ]
        for name, selector in submission.env_secrets.items():
            secret_id, version_id = split_secret_selector(selector)
            env_vars.append(
                JobSpec.EnvironmentVariable(
                    name=name,
                    mysterybox_secret=JobSpec.MysteryBoxSecretRef(
                        secret_id=secret_id, version_id=version_id
                    ),
                )
            )
        registry_credentials = None
        if submission.registry_secret:
            registry_credentials = JobSpec.RegistryCredentials(
                mysterybox_secret_version=submission.registry_secret
            )
        request = CreateJobRequest(
            metadata=ResourceMetadata(parent_id=submission.parent_id, name=submission.name),
            spec=JobSpec(
                image=submission.image,
                container_command=submission.command,
                args=shell_join_args(submission.args),
                platform=submission.platform,
                preset=submission.preset,
                timeout=timedelta(seconds=submission.timeout_seconds),
                subnet_id=submission.subnet_id,
                disk=JobSpec.DiskSpec(
                    type=ComputeDiskSpec.DiskType.NETWORK_SSD,
                    size_bytes=submission.disk_gib * 1024**3,
                ),
                restart_attempts=0,
                environment_variables=env_vars,
                registry_credentials=registry_credentials,
            ),
        )
        operation = self._service().create(request).wait()
        return operation.resource_id

    def get_job_state(self, job_id: str) -> str:
        from nebius.api.nebius.ai.v1 import GetJobRequest

        job = self._service().get(GetJobRequest(id=job_id)).wait()
        state = job.status.state
        return state.name if hasattr(state, "name") else str(state)


def shell_join_args(args: list[str]) -> str:
    """Preserve each validated argv item across Nebius' shell command boundary."""
    return shlex.join(args)
