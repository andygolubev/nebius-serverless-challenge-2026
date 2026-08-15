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
REWARD_VERSION = "locomotion-rewards-v15"
SCENE_VERSION = "custom-locomotion-scenes-v3"
PREPARATION_PROFILE_VERSION = "custom-prepare-v1"
TRAINING_PROFILE_VERSION = "custom-ppo-quick-v3"

# Fraction of evaluation episodes that must succeed for ``task_threshold_achieved``.
#
# v10 and earlier required *every* episode.  Evaluation is a twenty-seed sample of a
# stochastic rollout, so an all-or-nothing gate scores luck rather than the policy: at a
# per-episode success rate of 0.95 it reports failure about two runs in three, and even a
# policy that fails one episode in a hundred is badged red 18% of the time.  Measured on
# Nebius, the biped scored 19/20 -- nineteen near-identical episodes at height 0.523-0.545
# and upright 0.995-1.000, one seed tipping at step 134 -- and was reported as below
# threshold.  0.9 is the same tolerance the G1 showcase gates already moved to for exactly
# this reason, and it passes 92.5% of the time at 0.95 while still failing a genuinely
# unreliable policy: 12% of episodes lost is still a red badge.
TASK_SUCCESS_RATE_THRESHOLD = 0.9

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
    # The progress evaluation picks which checkpoint ships, so it has to be able to tell
    # checkpoints apart.  At four episodes it cannot: the standard error on a true rate
    # of 0.9 is +-0.15, and a measured biped stand-balance run read a flat 1.00 at five
    # consecutive checkpoints, of which the one published scored 0.55 over the twenty
    # evaluation seeds.  Selection among those five was a lottery.  Twelve episodes puts
    # the standard error at +-0.087 for about 4% more environment steps, against a
    # three-hour timeout that measured runs finish inside two.
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
        # How tall to stand, as a fraction of ``reference_height``.
        #
        # Per robot type, because ``reference_height`` does not mean the same thing for
        # both.  It is the height the robot rests at under zero control, and how much of
        # that a robot can still use once it has to hold itself up depends on its
        # morphology: the biped's spawn pose is already a standing pose and it keeps 88%
        # of it, while the quadruped spawns with its legs extended beneath it and adopts
        # a bent-leg stance at ~53% — normal for the shape, not a crouch.
        #
        # A single scale was tried both ways and each choice broke one robot.  Measured
        # at the production profile (16 envs, VecNormalize, 256x256, 3M steps):
        #
        #   robot       scale   asks for   reaches   stand   walk
        #   quadruped   0.575     0.339     0.318    20/20   17-20/20
        #   quadruped   0.900     0.530     0.264     0/20   19/20 crawling
        #   biped       0.575     0.537     0.539    19/20   20/20 crouched
        #   biped       0.900     0.840     0.822    (below) 20/20 upright
        #
        # The quadruped gets *worse* when asked for more, which is the height term's
        # Gaussian going flat: its width is target*0.25, so at an unreachable target the
        # gradient vanishes and the policy drops height to buy velocity instead.
        #
        # The biped stands at 18/20 here, which clears the 0.9 rate but only just, so 0.8
        # was measured as a candidate: it scores a clean 20/20 with zero falls, and it
        # crouches -- height 0.694 against 0.807-0.840, upright 0.970 against 0.999,
        # knees folded and torso pitched back.  Standing on near-straight legs is an
        # inverted pendulum with little recovery authority, so the two lost episodes buy
        # a posture that is actually standing.  That is the trade this contract takes;
        # do not "fix" the 18/20 by lowering this number without looking at the render.
        "target_height_scale": {"biped": 0.9, "quadruped": 0.575},
        # Lowered with the target so exploration has room to dip without terminating.
        "fall_height_scale": 0.35,
        "minimum_upright": 0.45,
        # The settle exists to let the model rest on the floor, because the authored
        # spawn height is not the resting height.  Contact is reached in about five
        # steps; every step after that is a robot standing under *zero torque*, which
        # for anything that does not balance passively is not settling but toppling.
        # Because ``reference_height`` is sampled at the end of the settle and every
        # threshold in this contract scales off it, that turned the success band into a
        # per-episode random variable.  Measured spread over the twenty evaluation
        # seeds: 0.0009 m at five steps against 0.2908 m (quadruped) and 0.3503 m
        # (biped) at twenty.  Worse, the low-reference episodes are the ones that
        # started already half-toppled -- ``qvel`` is zeroed afterwards, so the policy
        # inherits a stationary but collapsed pose it was never trained to leave.  That
        # was the whole of the biped's 25% fall rate.
        "settle_steps": 5,
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
        # Same per-morphology targets as stand-balance, and set from the same
        # measurements — see the table there.  Walking is where a mis-set target is most
        # visible: at 0.575 the biped crossed the arena folded onto one knee at 58% of
        # its stance and every metric called it a clean gait.
        "target_height_scale": {"biped": 0.9, "quadruped": 0.575},
        # Lowered with the target so the band above the fall line stays wide.
        "fall_height_scale": 0.35,
        "minimum_upright": 0.4,
        # Same five-step settle as stand-balance, and for the same reason: a reference
        # sampled off a toppling robot randomises the height reward's target and the
        # fall line together.  It mattered most here for the biped, whose resting
        # pelvis is 0.93 -- a twenty-step settle read it as low as 0.58, aiming the
        # height term at half the robot's stance and pointing its gradient at the floor.
        "settle_steps": 5,
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
        # Minimum body height for a rollout to count as walking, as a fraction of the
        # height this task's reward asked for — not of ``reference_height``, so it needs
        # no per-morphology table of its own and stays meaningful for any target.
        #
        # Without it the criterion was survive + velocity + drift and nothing else, so a
        # policy that crossed the arena folded down scored 20/20 and was reported as a
        # gait.  A floor stated against ``reference_height`` would have been the same
        # mistake one level down: 0.7 of it passes the biped and fails the quadruped
        # outright, which walks at 0.54 of its spawn height by nature.
        #
        # Measured fraction of target reached at the shipped targets: biped 0.97
        # (height 0.811 of 0.840), quadruped 0.88 (0.298 of 0.339); the crawl that
        # prompted this check reached 0.50.  0.8 clears both gaits -- every one of the
        # forty evaluation episodes across the two robots is above it -- and still
        # rejects the crawl.  The quadruped's 8 points of headroom is the tighter of the
        # two and is what to re-measure if this bar is ever raised: the point is to
        # reject a crawl, not to legislate how much a walking robot may bend its knees.
        "success_min_height_of_target": 0.8,
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
            #
            # Raised twice, from 0.6, because the tall gait was not worth reaching for.
            # At 0.6 the height term paid 0.11/step at the crouch the biped settled into
            # (0.571) against 0.59/step at the gait it should have, so the whole upright
            # posture was a ~13% reward improvement bought by raising the torso mid-stride
            # with a fall penalty if it goes wrong.  The Nebius run never took that trade:
            # success 0.000 at all twelve checkpoints while reward climbed 178 -> 3493.
            #
            # 1.2 moved it most of the way -- height 0.571 -> 0.720 and success 0.00 ->
            # 0.65 -- but left the distribution straddling the success floor of 0.672:
            # thirteen episodes landed at 0.683-0.822 and seven at 0.609-0.652, with every
            # episode surviving the full horizon, zero falls, velocity 0.75-0.79 and drift
            # under 0.15.  Height was the only thing separating pass from fail.
            #
            # 2.0 was measured and overshoots: the biped stood at 0.867 and stopped dead,
            # velocity 0.01, success 0.00.  It fails the velocity bound instead of the
            # posture floor.  1.5 bisects the bracket -- 1.2 walks at 0.720 with its worst
            # episode 0.063 short of the floor, 2.0 freezes -- and sits nearer the end
            # known to produce a gait.
            #
            # The trap is specific to the biped, and the quadruped shows why: it walks at
            # 0.314 and stands at 0.314, so no height weight can pay it to stop, and it
            # scored 0.95 at both 1.2 and 2.0.  The biped walks at ~0.72 but stands at
            # ~0.87, so every increase in this weight raises the payoff for freezing.
            # Note the reward still *prefers* walking at 2.0 -- a stationary robot loses
            # about 1.8/step on the velocity term against the ~0.5/step it gains on height
            # -- so this is PPO converging to the easy behaviour first, not the reward
            # ranking them wrongly.  Raising this further will not fix that; it deepens it.
            "height": 1.5,
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
        # DO NOT chase these numbers: this task is blocked on morphology, not thresholds.
        #
        # The reset rolls the body about world X, but the sample quadruped's eight
        # actuators are all ``axis="0 1 0"`` -- pitch only.  A body-Y torque has a world-X
        # component of exactly zero at every roll angle, so the robot has no actuator
        # authority about the one axis it must rotate; at a 69-83 degree roll the leg
        # swing plane is 0.93-0.99 vertical, so swinging the legs yaws the body instead of
        # righting it.  Measured: success 0.000 at every checkpoint through 3M, and
        # ``fall_rate`` 1.0 throughout -- it never once reached even ``minimum_upright``
        # 0.45, let alone ``success_upright`` 0.8.
        #
        # The height scales below are separately suspect -- 0.9 asks for 0.495 while the
        # same robot's converged standing policy holds 0.313-0.321, so the success bar of
        # 0.4125 also sits above its stance -- but rescaling them was measured and does
        # *not* make the task learnable, and it makes the height term pay 0.97 for lying
        # at the spawn pose.  They are left as they were until the reset is fixed: tipping
        # about pitch rather than roll is the change a pitch-only quadruped could act on,
        # and that needs its own verification.
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


# Spacing between the seed families the evaluation draws from.  Larger than any base seed
# so families cannot overlap; see ``evaluation_seeds``.
EVALUATION_SEED_STRIDE = 1000


def evaluation_seeds(base_seeds: tuple[int, ...], episodes: int) -> tuple[int, ...]:
    """The distinct initial conditions an evaluation scores, in order.

    The rule was ``base[index % len(base)] + index``, which collides whenever two base
    seeds differ by a multiple of the number of base seeds.  It does for the shipped
    twenty-episode profile: base 37 at index 2 and base 23 at index 16 both give 39, so
    the gate sampled nineteen initial conditions and counted one of them twice.  That is
    not a rounding detail — a measured biped run failed on exactly that seed and was
    scored 0.90 instead of the 18/19 = 0.947 it actually achieved, which is the
    difference between sitting on the threshold and clearing it.

    Walking the families apart by a stride larger than any base seed keeps the intent
    (one deterministic family per base seed) while making collisions impossible.
    """
    if episodes < 0:
        raise ValueError("episodes must not be negative")
    if not base_seeds:
        raise ValueError("at least one base seed is required")
    if len(set(base_seeds)) != len(base_seeds):
        raise ValueError("base seeds must be distinct")
    if max(base_seeds) >= EVALUATION_SEED_STRIDE:
        raise ValueError("base seeds must be smaller than the family stride")
    count = len(base_seeds)
    return tuple(
        base_seeds[index % count] + (index // count) * EVALUATION_SEED_STRIDE
        for index in range(episodes)
    )


def target_height_scale(task_id: str, robot_type: str) -> float:
    """Resolve ``target_height_scale``, which may be stated per robot type.

    A plain number applies to every robot type the task accepts; a mapping states one
    value per type and must cover all of them, so a robot type added to
    ``TASK_ROBOT_TYPES`` without a measured target fails loudly here rather than
    silently training against another morphology's number.
    """
    scale = TASK_CONTRACTS[task_id]["target_height_scale"]
    if not isinstance(scale, dict):
        return float(scale)
    if robot_type not in scale:
        raise KeyError(f"{task_id} has no target_height_scale for robot type {robot_type!r}")
    return float(scale[robot_type])

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
