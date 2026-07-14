"""Server-owned executable training catalog.

The public gallery is a small product contract, not a general job builder.  A
tenant selects one stable example ID and may change only the seed.  Images,
commands, environments, algorithms, compute, secrets and artifact prefixes are
derived here and validated again at the orchestration boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    type: str
    default: int | float
    min: int | float
    max: int | float


@dataclass(frozen=True)
class Algorithm:
    id: str
    label: str
    description: str
    params: tuple[Param, ...]


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
_COMMON_TUNING_PARAMS = (
    Param("learning_rate", "Learning rate", "float", 3e-4, 1e-5, 1e-2),
    SEED_PARAM,
)

ALGORITHMS: dict[str, Algorithm] = {
    "ppo-sb3": Algorithm(
        id="ppo-sb3",
        label="PPO (Stable-Baselines3)",
        description="CPU-vectorized MuJoCo PPO.",
        params=(
            Param(
                "total_timesteps",
                "Total timesteps",
                "int",
                1_000_000,
                10_000,
                5_000_000,
            ),
            *_COMMON_TUNING_PARAMS,
        ),
    ),
    "ppo-mjx": Algorithm(
        id="ppo-mjx",
        label="PPO (MJX / JAX)",
        description="GPU-parallel MuJoCo Playground PPO.",
        params=(
            Param(
                "total_timesteps",
                "Total timesteps",
                "int",
                100_000_000,
                10_000,
                100_000_000,
            ),
            *_COMMON_TUNING_PARAMS,
        ),
    ),
}

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

DEFAULT_PRESET = "go1-mjx-standard"
PRESETS: dict[str, dict[str, Any]] = {
    "go1-mjx-quick": {
        "label": "Go1 Quick",
        "description": "Fast GPU demo · observed about 20 min",
        "environment": "go1",
        "algorithm": "ppo-mjx",
        "params": {"total_timesteps": 5_000_000},
    },
    "go1-mjx-standard": {
        "label": "Go1 Standard",
        "description": "Balanced GPU run · observed about 21 min",
        "environment": "go1",
        "algorithm": "ppo-mjx",
        "params": {"total_timesteps": 25_000_000},
    },
    "go1-mjx-quality": {
        "label": "Go1 Quality",
        "description": "Flagship GPU result · observed about 27 min",
        "environment": "go1",
        "algorithm": "ppo-mjx",
        "params": {"total_timesteps": 100_000_000},
    },
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
            "go1-walker",
            "Go1 Walker",
            "Walk forward",
            "Train a quadruped to follow locomotion commands on flat terrain.",
            "Stable commanded walking with a replayable rollout.",
            "go1",
            "ppo-mjx",
            "NVIDIA H100",
            5_000_000,
            "Observed 18–22 min",
            "Observed $1.16–$1.41 at the current H100 rate",
            "velocity ≥ 0.5 m/s without falling",
            "Forward velocity",
            "go1-mjx-quick",
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
            "g1-rough-terrain",
            "G1 Rough Terrain",
            "Traverse rough ground",
            "Train a complex humanoid locomotion policy on uneven terrain.",
            "Command-following humanoid steps over rough terrain.",
            "g1",
            "ppo-mjx",
            "NVIDIA L40S candidate",
            25_000_000,
            "Acceptance measurement pending",
            "Acceptance measurement pending",
            "velocity ≥ 0.4 m/s without falling",
            "Forward velocity",
            "g1-rough-v1",
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


class ValidationError(Exception):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def job_spec(environment: str, algorithm: str) -> JobSpec | None:
    return JOB_SPECS.get((environment, algorithm))


def expand_preset(preset: str) -> dict[str, Any]:
    if preset not in PRESETS:
        raise ValidationError("preset", f"unknown preset: {preset}")
    value = PRESETS[preset]
    return {
        k: v for k, v in value.items() if k in {"environment", "algorithm", "params"}
    }


def _validate_params(algorithm: str, params: dict[str, Any]) -> dict[str, int | float]:
    algo = ALGORITHMS[algorithm]
    known = {p.name: p for p in algo.params}
    for name in params:
        if name not in known:
            raise ValidationError(name, f"unknown parameter for {algorithm}")
    resolved: dict[str, int | float] = {}
    for p in algo.params:
        value = params.get(p.name, p.default)
        if p.type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationError(p.name, "must be an integer")
        elif isinstance(value, bool) or not isinstance(value, int | float):
            raise ValidationError(p.name, "must be a number")
        else:
            value = float(value)
        if not p.min <= value <= p.max:
            raise ValidationError(p.name, f"must be between {p.min} and {p.max}")
        resolved[p.name] = value
    return resolved


def resolve_config(
    environment: str, algorithm: str, params: dict[str, Any]
) -> dict[str, Any]:
    env = ENVIRONMENTS.get(environment)
    if env is None:
        raise ValidationError("environment", f"unknown environment: {environment}")
    if algorithm not in env.algorithms:
        raise ValidationError(
            "algorithm", f"algorithm {algorithm!r} not available for {environment}"
        )
    if job_spec(environment, algorithm) is None:
        raise ValidationError(
            "algorithm", f"algorithm {algorithm!r} is not executable for {environment}"
        )
    return {
        "environment": environment,
        "algorithm": algorithm,
        "params": _validate_params(algorithm, params),
    }


def resolve_gallery(
    example_id: str,
    params: dict[str, Any],
    *,
    profile_id: str | None = None,
) -> dict[str, Any]:
    example = GALLERY_EXAMPLES.get(example_id)
    if example is None:
        raise ValidationError(
            "gallery_example_id", f"unknown gallery example: {example_id}"
        )
    spec = job_spec(example.environment, example.algorithm)
    if spec is None or spec.acceptance_revision != example.acceptance_revision:
        raise ValidationError(
            "gallery_example_id", "gallery example is not accepted for this release"
        )
    allowed = {p.name: p for p in example.optional_params}
    unknown = sorted(set(params) - set(allowed))
    if unknown:
        raise ValidationError(unknown[0], "field is not customizable for this example")
    selected_profile = profile_id or example.recommended_profile
    merged = dict(example.recommended_params)
    if example.id == "go1-walker":
        preset = PRESETS.get(selected_profile)
        if preset is None:
            raise ValidationError(
                "gallery_profile_id", "choose a Go1 catalog workload size"
            )
        merged.update(preset["params"])
    elif selected_profile != example.recommended_profile:
        raise ValidationError(
            "gallery_profile_id", "this example has one fixed recommended workload"
        )
    for name, value in params.items():
        bound = allowed[name]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(name, "must be an integer")
        if not bound.min <= value <= bound.max:
            raise ValidationError(name, f"must be between {bound.min} and {bound.max}")
        merged[name] = value
    return {
        "gallery_example_id": example.id,
        "example": {
            "id": example.id,
            "label": example.label,
            "avatar": example.avatar,
            "task": example.task,
        },
        "environment": example.environment,
        "algorithm": example.algorithm,
        "profile": selected_profile,
        "params": merged,
        "acceptance_revision": example.acceptance_revision,
        "success": {
            "criterion": example.success_criterion,
            "primary_metric": example.primary_metric,
        },
    }


def _serialized_example(example: GalleryExample) -> dict[str, Any]:
    value = asdict(example)
    value["optional_params"] = [asdict(item) for item in example.optional_params]
    value["workload_profiles"] = (
        [
            {"id": name, "recommended": name == "go1-mjx-quick", **preset}
            for name, preset in PRESETS.items()
        ]
        if example.id == "go1-walker"
        else []
    )
    return value


def serialize(*, gallery_enabled: bool = False) -> dict[str, Any]:
    examples = [
        _serialized_example(item)
        for item in GALLERY_EXAMPLES.values()
        if gallery_enabled
        and (spec := job_spec(item.environment, item.algorithm)) is not None
        and spec.acceptance_revision == item.acceptance_revision
    ]
    algorithms = ALGORITHMS.values() if gallery_enabled else (ALGORITHMS["ppo-mjx"],)
    environments = ENVIRONMENTS.values() if gallery_enabled else (ENVIRONMENTS["go1"],)
    return {
        "gallery_enabled": gallery_enabled,
        "examples": examples,
        "environments": [
            {
                "id": e.id,
                "label": e.label,
                "description": e.description,
                "algorithms": list(e.algorithms),
            }
            for e in environments
        ],
        "algorithms": [
            {
                "id": a.id,
                "label": a.label,
                "description": a.description,
                "params": [asdict(p) for p in a.params],
            }
            for a in algorithms
        ],
        "presets": [
            {"id": name, "default": name == DEFAULT_PRESET, **cfg}
            for name, cfg in PRESETS.items()
        ],
    }
