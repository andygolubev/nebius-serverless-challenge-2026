"""Single source of truth for what users can train.

Declares environments, per-environment policy algorithms, bounded hyperparameters, and
presets (named expansions). `GET /training-options` serializes it; job submission
validates against it — the frontend and the server can never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    type: str  # "int" | "float"
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
    algorithms: tuple[str, ...]  # compatible algorithm ids


_COMMON_TUNING_PARAMS = (
    Param("learning_rate", "Learning rate", "float", 3e-4, 1e-5, 1e-2),
    Param("seed", "Seed", "int", 0, 0, 2**31 - 1),
)

ALGORITHMS: dict[str, Algorithm] = {
    "ppo-sb3": Algorithm(
        id="ppo-sb3",
        label="PPO (Stable-Baselines3)",
        description="Dependable CPU-simulation baseline.",
        params=(
            Param("total_timesteps", "Total timesteps", "int", 100_000, 10_000, 5_000_000),
            *_COMMON_TUNING_PARAMS,
        ),
    ),
    "ppo-mjx": Algorithm(
        id="ppo-mjx",
        label="PPO (MJX / JAX)",
        description="Thousands of GPU-parallel simulations via MuJoCo Playground.",
        params=(
            Param("total_timesteps", "Total timesteps", "int", 100_000_000, 10_000, 100_000_000),
            *_COMMON_TUNING_PARAMS,
        ),
    ),
}

ENVIRONMENTS: dict[str, Environment] = {
    "go1": Environment(
        id="go1",
        label="Go1",
        description="Unitree Go1 quadruped — sim-to-real locomotion.",
        algorithms=("ppo-mjx",),
    ),
}

# Presets are named shortcuts that expand to a full configuration. The flagship
# MJX track is listed first and marked default; the composer pre-selects it.
DEFAULT_PRESET = "go1-mjx-standard"

PRESETS: dict[str, dict[str, Any]] = {
    "go1-mjx-quick": {"label": "Go1 Quick", "description": "Fast GPU demo · provisional 15–30 min", "environment": "go1", "algorithm": "ppo-mjx", "params": {"total_timesteps": 5_000_000}},
    "go1-mjx-standard": {"label": "Go1 Standard", "description": "Balanced GPU run · provisional 1–2 hr", "environment": "go1", "algorithm": "ppo-mjx", "params": {"total_timesteps": 25_000_000}},
    "go1-mjx-quality": {"label": "Go1 Quality", "description": "Flagship GPU result · up to 4 hr", "environment": "go1", "algorithm": "ppo-mjx", "params": {"total_timesteps": 100_000_000}},
}


@dataclass(frozen=True)
class JobSpec:
    """How one (environment, algorithm) combination runs as a Nebius Serverless AI job.

    Mirrors the parameters `sim2policy/jobs/submit.sh` requires. `param_paths` maps
    catalog parameter names to dotted config paths passed as `--set` overrides; only
    parameters listed here ever reach the container command line.
    """

    module: str  # python -m <module>
    config: str  # repo-relative base config inside the training image
    image_key: str  # runtime image selector: "sb3" | "mjx" (resolved from settings)
    platform: str
    preset: str  # Nebius compute preset (GPU/CPU shape), not a catalog preset
    timeout: str  # Nebius duration, also the poller's stuck-job bound
    max_total_timesteps: int
    param_paths: dict[str, str]


# MJX keeps the H100 shape verified by the full go1 run (docs/submission-checklist.md);
# SB3 simulation is CPU-bound with small policy networks, so it runs on the smallest
# documented L40S preset (jobs/README.md). Timeouts and step caps track
# configs/training_presets.yaml limits.
# The config loader only accepts two-level `section.key` overrides, so
# hyperparameters like learning_rate cannot be overridden per-job; tenants get
# the base config's value (train_sb3 rejects deeper dotted paths).
_SB3_PARAM_PATHS = {
    "total_timesteps": "training.total_steps",
    "seed": "seed",
}

JOB_SPECS: dict[tuple[str, str], JobSpec] = {
    ("go1", "ppo-mjx"): JobSpec(
        module="sim2policy.hosted_mjx",
        config="configs/go1_mjx.yaml",
        image_key="mjx",
        platform="gpu-h100-sxm",
        preset="1gpu-16vcpu-200gb",
        timeout="4h",
        max_total_timesteps=100_000_000,
        param_paths=_SB3_PARAM_PATHS,
    ),
}


def job_spec(environment: str, algorithm: str) -> JobSpec | None:
    return JOB_SPECS.get((environment, algorithm))


class ValidationError(Exception):
    """Field-level validation failure. `field` names the offending input."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def expand_preset(preset: str) -> dict[str, Any]:
    if preset not in PRESETS:
        raise ValidationError("preset", f"unknown preset: {preset}")
    value = PRESETS[preset]
    return {k: v for k, v in value.items() if k in {"environment", "algorithm", "params"}}


def resolve_config(environment: str, algorithm: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate against the catalog and merge overrides over defaults."""
    env = ENVIRONMENTS.get(environment)
    if env is None:
        raise ValidationError("environment", f"unknown environment: {environment}")
    if algorithm not in env.algorithms:
        allowed = ", ".join(env.algorithms)
        raise ValidationError("algorithm", f"algorithm {algorithm!r} not available for {environment} (allowed: {allowed})")
    if job_spec(environment, algorithm) is None:
        raise ValidationError("algorithm", f"algorithm {algorithm!r} is not executable for {environment}")
    algo = ALGORITHMS[algorithm]
    known = {p.name: p for p in algo.params}
    for name in params:
        if name not in known:
            raise ValidationError(name, f"unknown parameter for {algorithm}")
    resolved: dict[str, Any] = {}
    for p in algo.params:
        value = params.get(p.name, p.default)
        if p.type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationError(p.name, "must be an integer")
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(p.name, "must be a number")
            value = float(value)
        if not (p.min <= value <= p.max):
            raise ValidationError(p.name, f"must be between {p.min} and {p.max}")
        resolved[p.name] = value
    return {"environment": environment, "algorithm": algorithm, "params": resolved}


def serialize() -> dict[str, Any]:
    """Catalog as JSON for /training-options — what the frontend renders the composer from."""
    return {
        "environments": [
            {
                "id": e.id,
                "label": e.label,
                "description": e.description,
                "algorithms": list(e.algorithms),
            }
            for e in ENVIRONMENTS.values()
        ],
        "algorithms": [
            {
                "id": a.id,
                "label": a.label,
                "description": a.description,
                "params": [
                    {"name": p.name, "label": p.label, "type": p.type, "default": p.default, "min": p.min, "max": p.max}
                    for p in a.params
                ],
            }
            for a in ALGORITHMS.values() if a.id == "ppo-mjx"
        ],
        "presets": [{"id": name, "default": name == DEFAULT_PRESET, **cfg} for name, cfg in PRESETS.items()],
    }
