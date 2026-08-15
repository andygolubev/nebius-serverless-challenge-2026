"""Server-owned custom robot training eligibility and versioned profiles.

The SaaS image does not install the training package, so this module mirrors the small
wire-level constants in ``sim2policy.custom_robot_contract``.  A cross-package golden
test prevents either side from drifting.  Tenant requests never populate these values.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .models import PreparationAttempt, PreparationSummary, RobotAsset, RobotSetup

SCHEMA_VERSION = 2
ADAPTER_VERSION = "custom-robot-sb3-v2"
REWARD_VERSION = "locomotion-rewards-v20"
SCENE_VERSION = "custom-locomotion-scenes-v3"
PREPARATION_PROFILE_VERSION = "custom-prepare-v1"
TRAINING_PROFILE_VERSION = "custom-ppo-quick-v3"

SUPPORTED_TASKS = frozenset({"stand-balance", "walk-forward", "recover-from-fall"})
SUPPORTED_SCENES = frozenset(
    {"flat-arena", "ramp-course", "hurdle-course", "step-course"}
)
SUPPORTED_ROBOT_TYPES = frozenset({"biped", "quadruped"})
TASK_ROBOT_TYPES = {
    "stand-balance": SUPPORTED_ROBOT_TYPES,
    "walk-forward": SUPPORTED_ROBOT_TYPES,
    "recover-from-fall": frozenset({"quadruped"}),
}

REASON_FEATURE_DISABLED = "custom-training-not-enabled"
REASON_UNSUPPORTED_ROBOT_TYPE = "unsupported-robot-type"
REASON_UNSUPPORTED_TASK = "unsupported-task"
REASON_UNSUPPORTED_SCENE = "unsupported-scene"
REASON_OPTIONAL_OBJECTS = "optional-objects-not-supported"
REASON_NOT_PREPARED = "not-prepared"
REASON_PREPARING = "preparing"
REASON_PREPARATION_FAILED = "preparation-failed"
REASON_READY = "ready"

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reason: str


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
    """Locomotion training budget sized to converge rather than to smoke-test.

    v1 ran 100k timesteps on a serial ``DummyVecEnv``, which is roughly twelve PPO
    updates: not enough to learn to stand, and measured runs regressed after 25k steps.
    v2 keeps the same fixed, server-owned shape but spends real compute: subprocess
    vector environments across sixteen vCPUs, running observation/reward normalisation,
    and a budget in the range MuJoCo locomotion baselines actually need.
    """

    version: str = TRAINING_PROFILE_VERSION
    platform: str = "cpu-d3"
    preset: str = "16vcpu-64gb"
    disk_gib: int = 100
    timeout_seconds: int = 10_800
    cpu_count: int = 16
    memory_gib: int = 64
    max_input_bytes: int = 1024 * 1024
    max_artifact_bytes: int = 512 * 1024 * 1024
    total_timesteps: int = 3_000_000
    n_envs: int = 16
    checkpoint_every_steps: int = 250_000
    evaluation_every_steps: int = 250_000
    # Mirrors sim2policy.custom_robot_contract.TrainingProfile; see the comment there for
    # why four episodes could not tell checkpoints apart.  The cross-package golden test
    # fails if these drift.
    progress_evaluation_episodes: int = 12
    progress_evaluation_seeds: tuple[int, ...] = (101, 151, 199, 251)
    evaluation_episodes: int = 20
    evaluation_seeds: tuple[int, ...] = (11, 23, 37, 53, 71)
    ppo_learning_rate: float = 3e-4
    ppo_n_steps: int = 512
    ppo_batch_size: int = 512
    ppo_n_epochs: int = 10
    ppo_gamma: float = 0.99
    ppo_gae_lambda: float = 0.95
    ppo_clip_range: float = 0.2
    ppo_ent_coef: float = 0.0
    policy_net_arch: tuple[int, ...] = (256, 256)
    normalize_observations: bool = True
    normalize_reward: bool = True
    normalize_clip_obs: float = 10.0
    publish_best_checkpoint: bool = True
    hourly_rate: float = 0.3968
    currency: str = "USD"
    rate_date: str = "2026-07-14"


PREPARATION_PROFILE = PreparationProfile()
TRAINING_PROFILE = TrainingProfile()


def eligibility(setup: RobotSetup, *, enabled: bool = True) -> Eligibility:
    if not enabled:
        return Eligibility(False, REASON_FEATURE_DISABLED)
    if setup.robot_type not in SUPPORTED_ROBOT_TYPES:
        return Eligibility(False, REASON_UNSUPPORTED_ROBOT_TYPE)
    if setup.task_template_id not in SUPPORTED_TASKS:
        return Eligibility(False, REASON_UNSUPPORTED_TASK)
    if setup.robot_type not in TASK_ROBOT_TYPES[setup.task_template_id]:
        return Eligibility(False, REASON_UNSUPPORTED_TASK)
    if setup.scene_preset_id not in SUPPORTED_SCENES:
        return Eligibility(False, REASON_UNSUPPORTED_SCENE)
    return Eligibility(True, REASON_NOT_PREPARED)


def canonical_normalized_setup(setup: RobotSetup) -> dict[str, Any]:
    """Serialize only the closed, server-normalized world contract."""
    return {
        "schema_version": SCHEMA_VERSION,
        "robot_type": setup.robot_type,
        "task_template_id": setup.task_template_id,
        "scene_preset_id": setup.scene_preset_id,
        "objects": [item.model_dump(mode="json") for item in setup.objects],
    }


def project_setup_readiness(
    setup: RobotSetup,
    robot: RobotAsset,
    latest: PreparationAttempt | None,
    *,
    enabled: bool,
    runtime_image_digest: str,
) -> RobotSetup:
    allowed = eligibility(setup, enabled=enabled)
    if not allowed.eligible:
        return setup.model_copy(
            update={
                "trainable": False,
                "reason": allowed.reason,
                "training_readiness": "ineligible",
                "can_prepare": False,
                "can_start_training": False,
                "current_preparation": None,
            }
        )
    current_fingerprint = preparation_fingerprint(robot, setup, runtime_image_digest)
    current = (
        latest
        if latest is not None and latest.fingerprint == current_fingerprint
        else None
    )
    summary = (
        None
        if current is None
        else PreparationSummary.model_validate(current.model_dump(mode="json"))
    )
    state = "not_prepared"
    reason = REASON_NOT_PREPARED
    can_prepare = True
    can_start = False
    if current is not None and current.state in {"queued", "preparing"}:
        state, reason, can_prepare = "preparing", REASON_PREPARING, False
    elif current is not None and current.state == "accepted":
        state, reason, can_prepare, can_start = "ready", REASON_READY, False, True
    elif current is not None and current.state == "failed":
        state, reason = "preparation_failed", REASON_PREPARATION_FAILED
    return setup.model_copy(
        update={
            "trainable": can_start,
            "reason": reason,
            "training_readiness": state,
            "can_prepare": can_prepare,
            "can_start_training": can_start,
            "current_preparation": summary,
        }
    )


def resolved_custom_job(
    robot: RobotAsset,
    setup: RobotSetup,
    preparation: PreparationAttempt,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "job_kind": "custom-robot",
        "backend": "sb3",
        "profile": "custom-ppo-quick",
        "robot": {
            "id": robot.id,
            "name": robot.name,
            "robot_type": robot.robot_type,
            "digest": robot.digest,
        },
        "setup": {
            **canonical_normalized_setup(setup),
            "id": setup.id,
            "name": setup.name,
            "digest": setup.digest,
        },
        "preparation": {
            "id": preparation.id,
            "fingerprint": preparation.fingerprint,
            "profile_version": preparation.profile_version,
            "report_sha256": preparation.report_sha256,
        },
        "runtime": {"image_digest": preparation.runtime_image_digest},
        "adapter": {
            "version": ADAPTER_VERSION,
            "reward_version": REWARD_VERSION,
            "scene_version": SCENE_VERSION,
        },
        "training": {
            "profile": "custom-ppo-quick",
            "profile_version": TRAINING_PROFILE_VERSION,
            **asdict(TRAINING_PROFILE),
        },
    }


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def preparation_fingerprint(
    robot: RobotAsset,
    setup: RobotSetup,
    runtime_image_digest: str,
) -> str:
    if not SHA256_RE.fullmatch(robot.digest) or not SHA256_RE.fullmatch(setup.digest):
        raise ValueError("robot and setup digests must be lowercase SHA-256")
    if not runtime_image_digest or len(runtime_image_digest) > 256:
        raise ValueError("runtime image digest is required and must be bounded")
    return sha256_bytes(
        canonical_json(
            {
                "adapter_version": ADAPTER_VERSION,
                "preparation_profile_version": PREPARATION_PROFILE_VERSION,
                "reward_version": REWARD_VERSION,
                "robot_digest": robot.digest,
                "runtime_image_digest": runtime_image_digest,
                "schema_version": SCHEMA_VERSION,
                "setup_digest": setup.digest,
            }
        )
    )


def resolved_profile_payload() -> dict[str, Any]:
    preparation = asdict(PREPARATION_PROFILE)
    training = asdict(TRAINING_PROFILE)
    preparation["rollout_seeds"] = list(preparation["rollout_seeds"])
    training["evaluation_seeds"] = list(training["evaluation_seeds"])
    training["progress_evaluation_seeds"] = list(
        training["progress_evaluation_seeds"]
    )
    training["policy_net_arch"] = list(training["policy_net_arch"])
    return {"preparation": preparation, "training": training}


def build_input_documents(
    *,
    preparation_id: str,
    robot: RobotAsset,
    robot_xml: str,
    setup: RobotSetup,
    runtime_image_digest: str,
) -> tuple[bytes, bytes, dict[str, Any]]:
    if not SAFE_ID_RE.fullmatch(preparation_id):
        raise ValueError("preparation identity contains unsafe characters")
    robot_bytes = robot_xml.encode("utf-8")
    setup_bytes = canonical_json(canonical_normalized_setup(setup))
    fingerprint = preparation_fingerprint(robot, setup, runtime_image_digest)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "preparation_id": preparation_id,
        "fingerprint": fingerprint,
        "robot": {
            "id": robot.id,
            "path": "robot.xml",
            "source_digest": robot.digest,
            "sha256": sha256_bytes(robot_bytes),
            "size_bytes": len(robot_bytes),
        },
        "setup": {
            "id": setup.id,
            "path": "normalized-setup.json",
            "source_digest": setup.digest,
            "sha256": sha256_bytes(setup_bytes),
            "size_bytes": len(setup_bytes),
        },
        "runtime": {"image_digest": runtime_image_digest},
        "adapter_version": ADAPTER_VERSION,
        "reward_version": REWARD_VERSION,
        "preparation_profile_version": PREPARATION_PROFILE_VERSION,
    }
    return robot_bytes, setup_bytes, manifest
