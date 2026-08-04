"""Immutable, exact G1 flat-to-rough transition evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import load_checkpoint_metadata, metadata_path, sha256_file
from sim2policy.config import RunConfig
from sim2policy.g1_forward_env import (
    G1_FORWARD_FLAT_ENVIRONMENT,
    G1_FORWARD_ROUGH_ENVIRONMENT,
)

TRANSITION_RELATIVE_PATH = "report/g1-transition.json"
RESTORED_COMPONENTS = (
    "observation_normalizer",
    "policy_parameters",
    "value_parameters",
)
REINITIALIZED_COMPONENTS = (
    "optimizer_state",
    "learner_step",
    "rollout_state",
    "prng_state",
)


class TransitionError(ValueError):
    pass


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def write_immutable_local(path: Path, payload: dict[str, Any]) -> Path:
    """Atomically create a local transition record; permit identical replay only."""
    body = canonical_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        if path.read_bytes() != body:
            raise TransitionError("transition record already exists with different bytes") from exc
        return path
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def build_transition_record(
    *,
    parent_checkpoint: Path,
    parent_object_key: str,
    parent_sidecar_key: str,
    target_run_id: str,
    trainer_load_path: str,
    matrix_digest: str,
    image_digest: str,
    flat_config_digest: str,
    rough_config_digest: str,
    measured_flat_steps: int,
    remaining_rough_budget: int,
    requested_rough_steps: int,
    source_environment: str = G1_FORWARD_FLAT_ENVIRONMENT,
) -> dict[str, Any]:
    metadata = load_checkpoint_metadata(parent_checkpoint)
    if metadata.environment != source_environment:
        raise TransitionError("transition parent environment mismatch")
    if metadata.step > measured_flat_steps:
        raise TransitionError("transition parent step exceeds measured flat spend")
    sidecar = metadata_path(parent_checkpoint)
    return {
        "schema_version": 1,
        "source_environment": source_environment,
        "target_environment": G1_FORWARD_ROUGH_ENVIRONMENT,
        "target_run_id": target_run_id,
        "parent": {
            "object_key": parent_object_key,
            "sidecar_object_key": parent_sidecar_key,
            "checkpoint_name": parent_checkpoint.name,
            "sidecar_name": sidecar.name,
            "sidecar_step": metadata.step,
            "sha256": metadata.sha256,
            "sidecar_sha256": sha256_file(sidecar),
        },
        "digests": {
            "matrix": matrix_digest,
            "image": image_digest,
            "flat_config": flat_config_digest,
            "rough_config": rough_config_digest,
        },
        "budget": {
            "measured_flat_steps": measured_flat_steps,
            "remaining_rough_budget": remaining_rough_budget,
            "requested_rough_steps": requested_rough_steps,
        },
        "restore": {
            "brax_version": "0.14.2",
            "trainer_load_path": trainer_load_path,
            "restored_components": list(RESTORED_COMPONENTS),
            "reinitialized_components": list(REINITIALIZED_COMPONENTS),
            "fresh_initialization_seed": 0,
        },
    }


def verify_transition_record(
    record: dict[str, Any],
    *,
    parent_checkpoint: Path,
    target_config: RunConfig,
    matrix_digest: str,
    image_digest: str,
    flat_config_digest: str,
    rough_config_digest: str,
    target_run_id: str,
    trainer_load_path: str,
    source_environment: str = G1_FORWARD_FLAT_ENVIRONMENT,
) -> None:
    metadata = load_checkpoint_metadata(parent_checkpoint)
    parent = record.get("parent", {})
    digests = record.get("digests", {})
    restore = record.get("restore", {})
    budget = record.get("budget", {})
    expected = {
        "schema_version": 1,
        "source_environment": source_environment,
        "target_environment": G1_FORWARD_ROUGH_ENVIRONMENT,
        "target_run_id": target_run_id,
    }
    for name, value in expected.items():
        if record.get(name) != value:
            raise TransitionError(f"transition {name} mismatch")
    if target_config.environment != G1_FORWARD_ROUGH_ENVIRONMENT:
        raise TransitionError("transition target config is not fixed-forward rough G1")
    if metadata.environment != source_environment:
        raise TransitionError("transition parent environment mismatch")
    if (
        parent.get("checkpoint_name") != parent_checkpoint.name
        or parent.get("sidecar_name") != metadata_path(parent_checkpoint).name
        or parent.get("sidecar_step") != metadata.step
        or parent.get("sha256") != metadata.sha256
        or parent.get("sidecar_sha256") != sha256_file(metadata_path(parent_checkpoint))
    ):
        raise TransitionError("transition parent bytes, path, sidecar, or step mismatch")
    if digests != {
        "matrix": matrix_digest,
        "image": image_digest,
        "flat_config": flat_config_digest,
        "rough_config": rough_config_digest,
    }:
        raise TransitionError("transition digest binding mismatch")
    if restore != {
        "brax_version": "0.14.2",
        "trainer_load_path": trainer_load_path,
        "restored_components": list(RESTORED_COMPONENTS),
        "reinitialized_components": list(REINITIALIZED_COMPONENTS),
        "fresh_initialization_seed": 0,
    }:
        raise TransitionError("transition restore contract mismatch")
    measured = int(budget.get("measured_flat_steps", 0))
    remaining = int(budget.get("remaining_rough_budget", 0))
    requested = int(budget.get("requested_rough_steps", 0))
    if measured < metadata.step or requested <= 0 or requested > remaining:
        raise TransitionError("transition budget mismatch")
