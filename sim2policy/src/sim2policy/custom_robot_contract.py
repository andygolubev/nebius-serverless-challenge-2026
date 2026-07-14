"""Versioned, server-owned contracts for custom robot preparation and training.

This module intentionally contains no MuJoCo/SB3 imports.  The SaaS control plane and
the generic SB3 runtime can therefore share canonical profile, fingerprint, and JSON
contracts without importing accelerator dependencies or accepting tenant execution data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from importlib import resources
from typing import Any, cast

SCHEMA_VERSION = 1
ADAPTER_VERSION = "custom-robot-sb3-v1"
REWARD_VERSION = "locomotion-rewards-v1"
SCENE_VERSION = "custom-locomotion-scenes-v1"
PREPARATION_PROFILE_VERSION = "custom-prepare-v1"
TRAINING_PROFILE_VERSION = "custom-ppo-quick-v1"

SUPPORTED_ROBOT_TYPES = ("biped", "quadruped")
SUPPORTED_TASKS = ("stand-balance", "walk-forward")
SUPPORTED_SCENES = ("flat-arena", "ramp-course")

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PreparationProfile:
    version: str = PREPARATION_PROFILE_VERSION
    platform: str = "cpu-d3"
    preset: str = "4vcpu-16gb"
    disk_gib: int = 50
    timeout_seconds: int = 600
    cpu_count: int = 4
    memory_gib: int = 16
    max_input_bytes: int = 1024 * 1024
    manifest_timeout_seconds: int = 30
    compile_timeout_seconds: int = 45
    rollout_timeout_seconds: int = 120
    checker_timeout_seconds: int = 60
    render_timeout_seconds: int = 60
    learning_timeout_seconds: int = 240
    publish_timeout_seconds: int = 30
    rollout_steps: int = 512
    rollout_seeds: tuple[int, ...] = (7, 19, 43)
    smoke_learning_steps: int = 2048
    smoke_evaluation_episodes: int = 2
    max_render_bytes: int = 8 * 1024 * 1024
    max_report_bytes: int = 256 * 1024
    max_artifact_bytes: int = 16 * 1024 * 1024


@dataclass(frozen=True)
class TrainingProfile:
    version: str = TRAINING_PROFILE_VERSION
    platform: str = "cpu-d3"
    preset: str = "8vcpu-32gb"
    disk_gib: int = 100
    timeout_seconds: int = 3600
    cpu_count: int = 8
    memory_gib: int = 32
    max_input_bytes: int = 1024 * 1024
    max_artifact_bytes: int = 512 * 1024 * 1024
    total_timesteps: int = 100_000
    n_envs: int = 8
    checkpoint_every_steps: int = 25_000
    evaluation_every_steps: int = 25_000
    progress_evaluation_episodes: int = 2
    progress_evaluation_seeds: tuple[int, ...] = (101, 151)
    evaluation_episodes: int = 20
    evaluation_seeds: tuple[int, ...] = (11, 23, 37, 53, 71)
    ppo_learning_rate: float = 3e-4
    ppo_n_steps: int = 1024
    ppo_batch_size: int = 256
    ppo_n_epochs: int = 10
    ppo_gamma: float = 0.99
    ppo_gae_lambda: float = 0.95
    ppo_clip_range: float = 0.2
    hourly_rate: float = 0.1984
    currency: str = "USD"
    rate_date: str = "2026-07-14"


PREPARATION_PROFILE = PreparationProfile()
TRAINING_PROFILE = TrainingProfile()

OBSERVATION_BASE_FIELDS = (
    "root.height",
    "root.gravity_x",
    "root.gravity_y",
    "root.gravity_z",
    "root.linear_velocity_x",
    "root.linear_velocity_y",
    "root.linear_velocity_z",
    "root.angular_velocity_x",
    "root.angular_velocity_y",
    "root.angular_velocity_z",
)

TASK_CONTRACTS: dict[str, dict[str, Any]] = {
    "stand-balance": {
        "version": REWARD_VERSION,
        "episode_steps": 1000,
        "target_height_scale": 0.9,
        "fall_height_scale": 0.45,
        "minimum_upright": 0.45,
        "success_upright": 0.85,
        "success_height_tolerance": 0.25,
        "success_max_root_speed": 0.5,
        "weights": {
            "upright": 1.5,
            "height": 1.0,
            "root_motion": -0.08,
            "action": -0.01,
            "energy": -0.0005,
        },
    },
    "walk-forward": {
        "version": REWARD_VERSION,
        "episode_steps": 1000,
        "target_height_scale": 0.9,
        "fall_height_scale": 0.42,
        "minimum_upright": 0.4,
        "target_velocity": 0.8,
        "success_min_velocity": 0.35,
        "success_max_lateral_drift": 1.5,
        "weights": {
            "forward_velocity": 1.4,
            "upright": 0.8,
            "lateral_velocity": -0.15,
            "yaw_rate": -0.05,
            "action": -0.01,
            "energy": -0.0005,
        },
    },
}

SCENE_CONTRACTS: dict[str, dict[str, Any]] = {
    "flat-arena": {
        "version": SCENE_VERSION,
        "floor": {"type": "plane", "size": [12.0, 12.0, 0.1]},
        "ramp": None,
    },
    "ramp-course": {
        "version": SCENE_VERSION,
        "floor": {"type": "plane", "size": [12.0, 12.0, 0.1]},
        "ramp": {
            "position": [3.0, 0.0, 0.3],
            "half_size": [1.5, 1.0, 0.08],
            "pitch_degrees": -11.31,
        },
    },
}


def canonical_json(value: Any) -> bytes:
    """Return the single canonical JSON encoding used for digests and snapshots."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_safe_id(value: str, label: str = "identity") -> str:
    if not SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"{label} contains unsafe characters")
    return value


def preparation_fingerprint(
    *,
    robot_digest: str,
    setup_digest: str,
    runtime_image_digest: str,
    adapter_version: str = ADAPTER_VERSION,
    reward_version: str = REWARD_VERSION,
    preparation_profile_version: str = PREPARATION_PROFILE_VERSION,
) -> str:
    values = {
        "adapter_version": adapter_version,
        "preparation_profile_version": preparation_profile_version,
        "reward_version": reward_version,
        "robot_digest": robot_digest,
        "runtime_image_digest": runtime_image_digest,
        "schema_version": SCHEMA_VERSION,
        "setup_digest": setup_digest,
    }
    for label in ("robot_digest", "setup_digest"):
        if not SHA256_RE.fullmatch(str(values[label])):
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    if not runtime_image_digest or len(runtime_image_digest) > 256:
        raise ValueError("runtime_image_digest is required and must be bounded")
    return sha256_bytes(canonical_json(values))


def profile_payloads() -> dict[str, dict[str, Any]]:
    """JSON-safe profiles used in resolved configuration and golden fixtures."""

    def normalize(value: object) -> object:
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in value.items()}
        return value

    return {
        "preparation": normalize(asdict(PREPARATION_PROFILE)),  # type: ignore[dict-item]
        "training": normalize(asdict(TRAINING_PROFILE)),  # type: ignore[dict-item]
    }


def load_json_schema(name: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9-]+\.schema\.json", name):
        raise ValueError("unknown custom robot schema")
    path = resources.files("sim2policy").joinpath("schemas", "custom_robot", name)
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def contract_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "reward_version": REWARD_VERSION,
        "scene_version": SCENE_VERSION,
        "supported_robot_types": list(SUPPORTED_ROBOT_TYPES),
        "supported_tasks": list(SUPPORTED_TASKS),
        "supported_scenes": list(SUPPORTED_SCENES),
        "observation_base_fields": list(OBSERVATION_BASE_FIELDS),
        "task_contracts": TASK_CONTRACTS,
        "scene_contracts": SCENE_CONTRACTS,
        "profiles": profile_payloads(),
    }
