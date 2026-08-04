"""Nebius-only execution attestation for campaign workload entry points.

The repository can be edited and inspected on a developer workstation, but no
project workload is permitted to start there.  This module intentionally has no
cloud SDK dependency: the launcher obtains the provider identity and passes only
the small, non-secret attestation below into the process it starts.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


class ExecutionLocationError(RuntimeError):
    """Raised before a workload starts outside an approved Nebius resource."""


_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,255}$")
_REGION = re.compile(r"^[a-z]+-[a-z]+[0-9]+$")
_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{40,64}$")
_COMMAND_CLASSES = frozenset(
    {
        "test",
        "build",
        "import",
        "smoke",
        "campaign",
        "training",
        "evaluation",
        "render",
        "finalization",
        "verification",
    }
)


@dataclass(frozen=True)
class LocationAttestation:
    schema_version: int
    provider: str
    resource_id: str
    region: str
    immutable_revision: str
    command_class: str
    started_at: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_environment(environment: Mapping[str, str]) -> LocationAttestation:
    # AI job launchers must set the exact provider resource ID.  An instance ID
    # is accepted for preparation work performed over SSH on the builder VM.
    resource_id = (
        environment.get("SIM2POLICY_NEBIUS_RESOURCE_ID")
        or environment.get("NEBIUS_AI_JOB_ID")
        or environment.get("NEBIUS_COMPUTE_INSTANCE_ID")
    )
    region = environment.get("SIM2POLICY_NEBIUS_REGION") or environment.get("NEBIUS_REGION")
    revision = environment.get("SIM2POLICY_IMMUTABLE_REVISION")
    command_class = environment.get("SIM2POLICY_COMMAND_CLASS")
    if environment.get("SIM2POLICY_EXECUTION_LOCATION") != "nebius":
        raise ExecutionLocationError("NEEDS_HUMAN: EXECUTION_LOCATION_INVALID")
    if not resource_id or not _IDENTITY.fullmatch(resource_id):
        raise ExecutionLocationError("NEEDS_HUMAN: EXECUTION_LOCATION_INVALID")
    if not region or not _REGION.fullmatch(region):
        raise ExecutionLocationError("NEEDS_HUMAN: EXECUTION_LOCATION_INVALID")
    if not revision or not _DIGEST.fullmatch(revision.removeprefix("git:")):
        raise ExecutionLocationError("NEEDS_HUMAN: EXECUTION_LOCATION_INVALID")
    if command_class not in _COMMAND_CLASSES:
        raise ExecutionLocationError("NEEDS_HUMAN: EXECUTION_LOCATION_INVALID")
    return LocationAttestation(
        schema_version=1,
        provider="nebius",
        resource_id=resource_id,
        region=region,
        immutable_revision=revision,
        command_class=command_class,
        started_at=environment.get("SIM2POLICY_STARTED_AT") or _now(),
    )


def require_nebius_execution(
    command_class: str, *, environment: Mapping[str, str] | None = None
) -> LocationAttestation:
    """Validate the process location before importing or running workload code."""
    attestation = _read_environment(os.environ if environment is None else environment)
    if attestation.command_class != command_class:
        raise ExecutionLocationError("NEEDS_HUMAN: EXECUTION_LOCATION_INVALID")
    return attestation


def write_location_attestation(path: Path, attestation: LocationAttestation) -> Path:
    """Persist the deliberately small, credential-free evidence record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(attestation.to_dict(), indent=2, sort_keys=True) + "\n")
    return path
