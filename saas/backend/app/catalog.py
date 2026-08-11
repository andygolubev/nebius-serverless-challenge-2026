"""Server-owned training catalog and public showcase pinning.

The seven examples are display-and-evidence identities, not a job builder. Nothing
here is submittable: `JOB_SPECS` survives only as the record of what each curated
run executed, which is exactly the metadata the public showcase displays.

`SHOWCASE_RUNS` pins each example to one curated run in object storage. It is the
most security-relevant allowlist in the service — the showcase resolver's only
input is an example ID and its only output is a literal from this map — so it lives
in reviewable source rather than in configuration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    type: str
    default: int | float
    min: int | float
    max: int | float


@dataclass(frozen=True)
class Environment:
    id: str
    label: str
    description: str
    algorithms: tuple[str, ...]


@dataclass(frozen=True)
class JobSpec:
    module: str
    config: str
    image_key: str
    platform: str
    preset: str
    disk_gib: int
    timeout: str
    max_total_timesteps: int
    param_paths: dict[str, str]
    acceptance_revision: str
    hourly_rate: float
    rate_date: str


@dataclass(frozen=True)
class GalleryExample:
    id: str
    label: str
    task: str
    description: str
    avatar: str
    expected_result: str
    environment: str
    algorithm: str
    backend_label: str
    hardware_label: str
    recommended_profile: str
    recommended_params: dict[str, int | float]
    optional_params: tuple[Param, ...]
    observed_duration: str
    observed_cost: str
    success_criterion: str
    primary_metric: str
    acceptance_revision: str


SEED_PARAM = Param("seed", "Seed", "int", 0, 0, 2**31 - 1)
ENVIRONMENTS: dict[str, Environment] = {
    "go1": Environment(
        "go1", "Go1", "Flat-terrain quadruped locomotion.", ("ppo-mjx",)
    ),
    "ant": Environment(
        "ant", "Ant", "Multi-legged exploration and forward locomotion.", ("ppo-sb3",)
    ),
    "halfcheetah": Environment(
        "halfcheetah", "HalfCheetah", "Fast planar locomotion.", ("ppo-sb3",)
    ),
    "hopper": Environment(
        "hopper", "Hopper", "One-legged balance and forward hopping.", ("ppo-sb3",)
    ),
    "walker2d": Environment(
        "walker2d", "Walker2D", "Two-legged planar walking.", ("ppo-sb3",)
    ),
    "g1": Environment(
        "g1", "G1", "Humanoid locomotion over rough terrain.", ("ppo-mjx",)
    ),
    "reacher": Environment(
        "reacher", "Reacher", "Two-link arm target reaching.", ("ppo-sb3",)
    ),
}

_SB3_PARAM_PATHS = {"total_timesteps": "training.total_steps", "seed": "seed"}
_GALLERY_REVISION = "gallery-v1-2026-07-14"

JOB_SPECS: dict[tuple[str, str], JobSpec] = {
    ("go1", "ppo-mjx"): JobSpec(
        "sim2policy.hosted_mjx",
        "configs/go1_mjx.yaml",
        "mjx",
        "gpu-h100-sxm",
        "1gpu-16vcpu-200gb",
        100,
        "4h",
        100_000_000,
        _SB3_PARAM_PATHS,
        _GALLERY_REVISION,
        3.85,
        "2026-07-14",
    ),
    ("ant", "ppo-sb3"): JobSpec(
        "sim2policy.hosted_sb3",
        "configs/ant_gallery_sb3.yaml",
        "sb3",
        "cpu-d3",
        "8vcpu-32gb",
        100,
        "3h",
        1_000_000,
        _SB3_PARAM_PATHS,
        _GALLERY_REVISION,
        0.1984,
        "2026-07-14",
    ),
    ("halfcheetah", "ppo-sb3"): JobSpec(
        "sim2policy.hosted_sb3",
        "configs/halfcheetah_gallery_sb3.yaml",
        "sb3",
        "cpu-d3",
        "8vcpu-32gb",
        100,
        "2h",
        1_000_000,
        _SB3_PARAM_PATHS,
        _GALLERY_REVISION,
        0.1984,
        "2026-07-14",
    ),
    ("hopper", "ppo-sb3"): JobSpec(
        "sim2policy.hosted_sb3",
        "configs/hopper_sb3.yaml",
        "sb3",
        "cpu-d3",
        "8vcpu-32gb",
        100,
        "2h",
        2_000_000,
        _SB3_PARAM_PATHS,
        _GALLERY_REVISION,
        0.1984,
        "2026-07-14",
    ),
    ("walker2d", "ppo-sb3"): JobSpec(
        "sim2policy.hosted_sb3",
        "configs/walker2d_sb3.yaml",
        "sb3",
        "cpu-d3",
        "8vcpu-32gb",
        100,
        "3h",
        2_000_000,
        _SB3_PARAM_PATHS,
        _GALLERY_REVISION,
        0.1984,
        "2026-07-14",
    ),
    ("g1", "ppo-mjx"): JobSpec(
        "sim2policy.hosted_mjx",
        "configs/g1_mjx.yaml",
        "mjx",
        "gpu-l40s-a",
        "1gpu-8vcpu-32gb",
        100,
        "4h",
        25_000_000,
        _SB3_PARAM_PATHS,
        _GALLERY_REVISION,
        1.5484,
        "2026-07-14",
    ),
    ("reacher", "ppo-sb3"): JobSpec(
        "sim2policy.hosted_sb3",
        "configs/reacher_sb3.yaml",
        "sb3",
        "cpu-d3",
        "8vcpu-32gb",
        100,
        "1h",
        300_000,
        _SB3_PARAM_PATHS,
        _GALLERY_REVISION,
        0.1984,
        "2026-07-14",
    ),
}


def _example(
    id: str,
    label: str,
    task: str,
    description: str,
    expected: str,
    environment: str,
    algorithm: str,
    hardware: str,
    steps: int,
    duration: str,
    cost: str,
    criterion: str,
    metric: str,
    profile: str,
) -> GalleryExample:
    return GalleryExample(
        id=id,
        label=label,
        task=task,
        description=description,
        avatar=f"/avatars/{id}.svg",
        expected_result=expected,
        environment=environment,
        algorithm=algorithm,
        backend_label="MJX / JAX PPO" if algorithm == "ppo-mjx" else "SB3 PPO",
        hardware_label=hardware,
        recommended_profile=profile,
        recommended_params={"total_timesteps": steps, "seed": 0},
        optional_params=(SEED_PARAM,),
        observed_duration=duration,
        observed_cost=cost,
        success_criterion=criterion,
        primary_metric=metric,
        acceptance_revision=_GALLERY_REVISION,
    )


GALLERY_EXAMPLES: dict[str, GalleryExample] = {
    item.id: item
    for item in (
        _example(
            "g1-rough-terrain",
            "G1 Rough Terrain",
            "Traverse rough ground",
            "Train a complex humanoid locomotion policy on uneven terrain.",
            "Command-following humanoid steps over rough terrain.",
            "g1",
            "ppo-mjx",
            "NVIDIA H100",
            450_000_000,
            "Observed about 4 h 7 min end to end",
            "About $6.80 training runtime · about $7.80 end to end",
            "velocity ≥ 0.4 m/s without falling",
            "Forward velocity",
            "g1-rough-v1",
        ),
        _example(
            "go1-walker",
            "Go1 Walker",
            "Walk forward",
            "Train a quadruped to follow locomotion commands on flat terrain.",
            "Stable commanded walking with a replayable rollout.",
            "go1",
            "ppo-mjx",
            "NVIDIA H100",
            100_000_000,
            "Observed about 25 min end to end",
            "Measured $0.69 training runtime · about $1.67 end to end",
            "velocity ≥ 0.5 m/s without falling",
            "Forward velocity",
            "go1-mjx-quality",
        ),
        _example(
            "ant-explorer",
            "Ant Explorer",
            "Explore forward",
            "Coordinate eight joints to move a four-legged ant efficiently.",
            "A coordinated forward gait with increasing episode reward.",
            "ant",
            "ppo-sb3",
            "CPU D3 · 8 vCPU",
            1_000_000,
            "Observed about 12 min",
            "Observed about $0.04",
            "mean reward ≥ 1000",
            "Mean reward",
            "ant-gallery-v1",
        ),
        _example(
            "halfcheetah-sprint",
            "HalfCheetah Sprint",
            "Sprint",
            "Learn a fast planar running gait with six continuous actuators.",
            "A visibly faster, stable running cycle.",
            "halfcheetah",
            "ppo-sb3",
            "CPU D3 · 8 vCPU",
            1_000_000,
            "Observed about 8 min",
            "Observed about $0.03",
            "mean reward ≥ 1500",
            "Mean reward",
            "halfcheetah-gallery-v1",
        ),
        _example(
            "hopper-balance",
            "Hopper Balance",
            "Balance and hop",
            "Keep a one-legged robot upright while making forward progress.",
            "Longer upright episodes and controlled hopping.",
            "hopper",
            "ppo-sb3",
            "CPU D3 · 8 vCPU",
            2_000_000,
            "Observed about 13 min",
            "Observed about $0.04",
            "mean reward ≥ 1000",
            "Mean reward",
            "hopper-gallery-v1",
        ),
        _example(
            "walker2d-stride",
            "Walker2D Stride",
            "Build a stride",
            "Train a planar biped to alternate legs without collapsing.",
            "A repeatable two-legged forward stride.",
            "walker2d",
            "ppo-sb3",
            "CPU D3 · 8 vCPU",
            2_000_000,
            "Observed about 14 min",
            "Observed about $0.05",
            "mean reward ≥ 1800",
            "Mean reward",
            "walker2d-gallery-v1",
        ),
        _example(
            "reacher-target",
            "Reacher Target",
            "Reach a target",
            "Control a two-link arm to place its fingertip near a moving target.",
            "Accurate target reaching with a compact policy.",
            "reacher",
            "ppo-sb3",
            "CPU D3 · 8 vCPU",
            300_000,
            "Observed about 5 min",
            "Observed about $0.02",
            "mean reward ≥ -10",
            "Mean reward",
            "reacher-gallery-v1",
        ),
    )
}


# -- public showcase pinning -----------------------------------------------------------

# The same safe pattern the orchestration boundary enforces on run identities.
SHOWCASE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# A tenant job id is `uuid4().hex`: exactly 32 lowercase hex characters. A pinned
# showcase run must never be mistakable for one, because both share the artifact
# cache keyspace and a collision would let a showcase lookup surface tenant data.
_TENANT_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
# Marks an example whose curated run has not been performed yet (a separate change
# performs them). A placeholder resolves to no run at all, so nothing is read from
# storage and the entry simply stays unpublished.
PENDING_RUN_PREFIX = "pending-curated-run-"

SHOWCASE_RUNS: dict[str, str] = {
    "go1-walker": "showcase-gallery-go1-20260802-17-go1-s0",
    "ant-explorer": "showcase-gallery-ant-20260801-12-ant-s7",
    "halfcheetah-sprint": "showcase-gallery-hc-20260801-11-halfcheetah-s7",
    "hopper-balance": "showcase-gallery-result-20260730-07-hopper-s7",
    "walker2d-stride": "showcase-gallery-w2d-20260801-13-walker2d-s42",
    "g1-rough-terrain": "showcase-gallery-g1-survival-20260811-01-g1-s0-rough",
    "reacher-target": "showcase-gallery-result-20260730-07-reacher-s42",
}

_validated_runs: dict[str, str] | None = None


def is_pending_run(run_id: str) -> bool:
    return run_id.startswith(PENDING_RUN_PREFIX)


def _reject(example_id: str, reason: str) -> None:
    # Sanitized: the rejected value is never logged, only which entry and why.
    log.warning("showcase entry %s is not publishable: %s", example_id, reason)


def validate_showcase_runs() -> dict[str, str]:
    """Return the pinned runs that are safe to serve, rejecting the rest.

    One bad literal must not take the service down while the other entries are
    fine, so a rejected entry is logged and left unpublished instead of raising.
    """
    global _validated_runs
    duplicated = {
        run_id
        for run_id in SHOWCASE_RUNS.values()
        if list(SHOWCASE_RUNS.values()).count(run_id) > 1
    }
    valid: dict[str, str] = {}
    for example_id, run_id in SHOWCASE_RUNS.items():
        if example_id not in GALLERY_EXAMPLES:
            _reject(example_id, "not a known gallery example")
        elif not isinstance(run_id, str) or not SHOWCASE_RUN_ID_RE.fullmatch(run_id):
            _reject(example_id, "pinned run identity is not a safe identifier")
        elif "/" in run_id or ".." in run_id.split("."):
            # Belt-and-braces containment: the reader builds `sim2policy/<run>/<rel>`,
            # so a run identity must be exactly one safe path segment.
            _reject(example_id, "pinned run identity is not a single safe path segment")
        elif _TENANT_JOB_ID_RE.fullmatch(run_id):
            _reject(example_id, "pinned run identity collides with the tenant job space")
        elif run_id in duplicated:
            # If two examples claim the same run, neither claim is trustworthy.
            _reject(example_id, "pinned run identity is claimed by another example")
        else:
            valid[example_id] = run_id
    _validated_runs = valid
    return valid


def resolve_showcase_run(example_id: str) -> str | None:
    """Map an example ID to its pinned curated run, or None if there is not one.

    This is the showcase's entire identity resolution. It takes no run ID, job ID,
    storage key, or prefix, and it returns only a literal from `SHOWCASE_RUNS`, so
    no caller-supplied value can ever select what is read from storage. `None`
    covers an unknown example, a rejected pinning, and a run not yet performed.
    """
    runs = _validated_runs if _validated_runs is not None else validate_showcase_runs()
    run_id = runs.get(example_id)
    if run_id is None or is_pending_run(run_id):
        return None
    return run_id


def job_spec(environment: str, algorithm: str) -> JobSpec | None:
    return JOB_SPECS.get((environment, algorithm))
