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

SCHEMA_VERSION = 2
ADAPTER_VERSION = "custom-robot-sb3-v2"
REWARD_VERSION = "locomotion-rewards-v9"
SCENE_VERSION = "custom-locomotion-scenes-v3"
PREPARATION_PROFILE_VERSION = "custom-prepare-v1"
TRAINING_PROFILE_VERSION = "custom-ppo-quick-v2"

SUPPORTED_ROBOT_TYPES = ("biped", "quadruped")
SUPPORTED_TASKS = ("stand-balance", "walk-forward", "recover-from-fall")
SUPPORTED_SCENES = ("flat-arena", "ramp-course", "hurdle-course", "step-course")
TASK_ROBOT_TYPES = {
    "stand-balance": SUPPORTED_ROBOT_TYPES,
    "walk-forward": SUPPORTED_ROBOT_TYPES,
    "recover-from-fall": ("quadruped",),
}
MAX_OBJECTS = 6

OBJECT_CONTRACTS: dict[str, dict[str, tuple[float, float]]] = {
    "box": {
        "x": (-10.0, 10.0), "y": (-10.0, 10.0), "z": (0.0, 5.0),
        "yaw_degrees": (-180.0, 180.0), "width": (0.1, 4.0),
        "depth": (0.1, 4.0), "height": (0.05, 2.0),
    },
    "ramp": {
        "x": (-10.0, 10.0), "y": (-10.0, 10.0), "z": (0.0, 5.0),
        "yaw_degrees": (-180.0, 180.0), "width": (0.5, 4.0),
        "depth": (0.5, 6.0), "height": (0.1, 2.0),
    },
    "hurdle": {
        "x": (-10.0, 10.0), "y": (-10.0, 10.0), "z": (0.0, 5.0),
        "yaw_degrees": (-180.0, 180.0), "width": (0.5, 4.0),
        "depth": (0.05, 0.5), "height": (0.05, 1.5),
    },
    "step": {
        "x": (-10.0, 10.0), "y": (-10.0, 10.0), "z": (0.0, 5.0),
        "yaw_degrees": (-180.0, 180.0), "width": (0.2, 4.0),
        "depth": (0.2, 4.0), "height": (0.05, 0.75),
    },
}

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
    progress_evaluation_episodes: int = 4
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
    # Where the robot is relative to the line it was asked to walk, and which way it is
    # pointing.  Adapter v1 exposed neither: the gravity vector is invariant to yaw and
    # the velocities are expressed in the root frame, so a policy could not perceive
    # heading error or accumulated sideways displacement at all.  walk-forward success
    # bounds exactly that displacement, and measured runs drifted 4-13 m off the line
    # while walking at the commanded speed — unobservable, therefore unlearnable, no
    # matter how the reward was shaped.  Present for every task; for the stationary
    # tasks they simply sit near zero.
    "root.lateral_offset",
    "root.heading_cos",
    "root.heading_sin",
)

TASK_CONTRACTS: dict[str, dict[str, Any]] = {
    "stand-balance": {
        "version": REWARD_VERSION,
        "episode_steps": 1000,
        # v3 scaled the target off ``reference_height``, which is sampled after only
        # ``settle_steps`` of zero control — while a primitive robot is still dropping.
        # For the sample quadruped that reads 0.4457, putting the success band at
        # [0.301, 0.501]; the tallest posture it can actually hold is ~0.29, so every
        # run scored success_rate 0 no matter how long it trained. Measured locally at
        # the production profile (16 envs, VecNormalize, 256x256): baseline 0.10 vs
        # 0.90 here, both converging to h~0.27 — the ceiling is the robot's geometry,
        # not the training budget. 0.575 centres the band on that reachable height.
        "target_height_scale": 0.575,
        # Lowered with the target so exploration has room to dip without terminating.
        "fall_height_scale": 0.35,
        "minimum_upright": 0.45,
        "settle_steps": 20,
        "success_upright": 0.85,
        "success_height_tolerance": 0.25,
        "success_max_root_speed": 0.5,
        "weights": {
            "alive": 1.0,
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
        # v4 carried the same 0.9 scale that was measured wrong for stand-balance: it is
        # taken off ``reference_height`` (0.4457 for the sample quadruped), so it asked
        # for a 0.401 body height that a primitive robot cannot hold — the tallest
        # posture it can sustain is ~0.29.  0.575 centres the height term on the posture
        # the robot actually walks at.
        "target_height_scale": 0.575,
        # Lowered with the target so the band above the fall line stays wide.
        "fall_height_scale": 0.35,
        "minimum_upright": 0.4,
        "settle_steps": 20,
        "target_velocity": 0.8,
        # Width of the Gaussian used to score forward velocity against
        # ``target_velocity``.  v2 rewarded raw unbounded velocity, which paid more for
        # diving forward than for walking at the commanded speed.
        "velocity_tolerance": 0.5,
        # Width of the Gaussian scoring lateral offset, set to half
        # ``success_max_lateral_drift`` so the reward starts falling away well before the
        # robot reaches the drift bound rather than at it.
        "lateral_tolerance": 0.75,
        "success_min_velocity": 0.35,
        "success_max_lateral_drift": 1.5,
        "weights": {
            # Halved from the balance tasks' 1.0.  Standing still collected
            # alive + upright + height ~= 2.6 per step for free while walking added at
            # most 1.4 on top, so a dead stop was a cheap, safe local optimum: measured
            # v8 episodes split into walkers and robots that took a few steps and then
            # stopped at exactly zero velocity for the rest of the horizon.  Surviving
            # still has to pay something — it is what keeps the robot off the floor —
            # just not enough to compete with the task.
            "alive": 0.5,
            # Raised with the same intent: forward motion should be where the reward is.
            "forward_velocity": 2.0,
            "upright": 1.0,
            # v4 scored no body height at all while walking, so nothing opposed a policy
            # that crept lower and lower until it clipped the fall line: measured runs
            # stayed upright but fell in 20% of evaluation episodes.
            "height": 0.6,
            # A cost, not a bonus — see the reward term for why v7's bonus form taught
            # the robot to stand still.  Kept below the forward-velocity weight so that
            # walking off course still beats not walking at all.
            "lateral_offset": -1.0,
            "lateral_velocity": -0.15,
            "yaw_rate": -0.05,
            "action": -0.01,
            "energy": -0.0005,
        },
    },
    "recover-from-fall": {
        "version": REWARD_VERSION,
        "episode_steps": 1000,
        "target_height_scale": 0.9,
        "fall_height_scale": 0.45,
        "minimum_upright": 0.45,
        "reset_roll_radians": [1.2, 1.45],
        "reset_height_scale": 0.55,
        "settle_steps": 0,
        "success_upright": 0.8,
        "success_height_scale": 0.75,
        "success_max_root_speed": 0.75,
        "weights": {
            "alive": 1.0,
            "upright": 1.8,
            "height": 1.2,
            "root_motion": -0.04,
            "action": -0.01,
            "energy": -0.0005,
        },
    },
}

SCENE_CONTRACTS: dict[str, dict[str, Any]] = {
    "flat-arena": {
        "version": SCENE_VERSION,
        "floor": {"type": "plane", "size": [30.0, 30.0, 0.1]},
        "preset_objects": [],
    },
    "ramp-course": {
        "version": SCENE_VERSION,
        "floor": {"type": "plane", "size": [30.0, 30.0, 0.1]},
        "preset_objects": [
            {"object_type": "ramp", "x": 3.0, "y": 0.0, "z": 0.0,
             "yaw_degrees": 0.0, "width": 1.5, "depth": 3.0,
             "height": 0.6, "source": "preset"}
        ],
    },
    "hurdle-course": {
        "version": SCENE_VERSION,
        "floor": {"type": "plane", "size": [30.0, 30.0, 0.1]},
        "preset_objects": [
            {"object_type": "hurdle", "x": x, "y": 0.0, "z": 0.0,
             "yaw_degrees": 0.0, "width": 2.0, "depth": 0.15,
             "height": 0.35, "source": "preset"}
            for x in (2.0, 4.0, 6.0)
        ],
    },
    "step-course": {
        "version": SCENE_VERSION,
        "floor": {"type": "plane", "size": [30.0, 30.0, 0.1]},
        "preset_objects": [
            {"object_type": "step", "x": x, "y": 0.0, "z": 0.0,
             "yaw_degrees": 0.0, "width": 2.0, "depth": 1.0,
             "height": height, "source": "preset"}
            for x, height in ((2.0, 0.2), (4.0, 0.3), (6.0, 0.4))
        ],
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
        "task_robot_types": TASK_ROBOT_TYPES,
        "supported_scenes": list(SUPPORTED_SCENES),
        "max_objects": MAX_OBJECTS,
        "object_contracts": OBJECT_CONTRACTS,
        "observation_base_fields": list(OBSERVATION_BASE_FIELDS),
        "task_contracts": TASK_CONTRACTS,
        "scene_contracts": SCENE_CONTRACTS,
        "profiles": profile_payloads(),
    }
