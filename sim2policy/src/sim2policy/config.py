from __future__ import annotations

import dataclasses
import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

import yaml

Backend = Literal["sb3", "mjx"]
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")
_SECRET_KEYS = {"access_key", "secret_key", "session_token", "password", "token"}
T = TypeVar("T")


class ConfigError(ValueError):
    """Raised when configuration cannot be safely resolved."""


@dataclass(frozen=True)
class TrainingConfig:
    total_steps: int
    n_envs: int
    device: str = "auto"
    hyperparameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckpointConfig:
    every_steps: int
    keep: int = 0


@dataclass(frozen=True)
class EvaluationConfig:
    episodes: int = 20
    seeds: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])


@dataclass(frozen=True)
class SuccessConfig:
    kind: Literal["mean_reward", "locomotion"]
    threshold: float | None = None
    min_velocity: float | None = None
    target_velocity: float = 1.0
    require_not_fallen: bool = True


@dataclass(frozen=True)
class RenderingConfig:
    frames: int = 500
    fps: int = 30
    width: int = 640
    height: int = 480
    seed: int = 0


@dataclass(frozen=True)
class StorageConfig:
    mode: Literal["local", "s3"] = "local"
    bucket: str | None = None
    prefix: str = "sim2policy"
    endpoint_url: str | None = None
    region: str | None = None
    retries: int = 3


@dataclass(frozen=True)
class ReportingConfig:
    hourly_rate: float | None = None
    currency: str | None = None
    rate_date: str | None = None


@dataclass(frozen=True)
class RunConfig:
    backend: Backend
    environment: str
    seed: int
    training: TrainingConfig
    checkpoint: CheckpointConfig
    evaluation: EvaluationConfig
    success: SuccessConfig
    rendering: RenderingConfig = field(default_factory=RenderingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)

    def to_dict(self, *, redact: bool = True) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        return redact_mapping(data) if redact else data

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)


_SECTIONS: dict[str, type[Any]] = {
    "training": TrainingConfig,
    "checkpoint": CheckpointConfig,
    "evaluation": EvaluationConfig,
    "success": SuccessConfig,
    "rendering": RenderingConfig,
    "storage": StorageConfig,
    "reporting": ReportingConfig,
}


def _construct(cls: type[T], raw: Any, section: str) -> T:
    if not isinstance(raw, dict):
        raise ConfigError(f"{section} must be a mapping")
    fields = dataclasses.fields(cast(Any, cls))
    allowed = {item.name for item in fields}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigError(f"unknown {section} setting(s): {', '.join(unknown)}")
    required = {
        item.name
        for item in fields
        if item.default is dataclasses.MISSING and item.default_factory is dataclasses.MISSING
    }
    missing = sorted(required - set(raw))
    if missing:
        raise ConfigError(f"missing {section} setting(s): {', '.join(missing)}")
    return cls(**raw)


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id) or run_id in {".", ".."}:
        raise ConfigError(
            "run ID must be 1-128 safe alphanumeric, dot, underscore, or dash characters"
        )
    return run_id


def validate_prefix(prefix: str) -> str:
    if (
        not SAFE_PREFIX_PATTERN.fullmatch(prefix)
        or prefix.startswith("/")
        or prefix.endswith("/")
        or any(part in {"", ".", ".."} for part in prefix.split("/"))
    ):
        raise ConfigError("storage prefix must be a relative safe object-key prefix")
    return prefix


def parse_override(value: str) -> tuple[str, Any]:
    """Parse one CLI override while keeping the result safe for JSON metadata.

    Serverless AI transports the argument vector as one joined command string, so
    quotes around an ISO date can be removed before Python receives it. PyYAML then
    yields ``datetime.date``; normalize that implicit type at the single shared edge.
    """
    key, separator, raw = value.partition("=")
    if not separator:
        raise ConfigError("override must be KEY=YAML_VALUE")
    parsed = yaml.safe_load(raw)
    if isinstance(parsed, (datetime.date, datetime.datetime)):
        parsed = parsed.isoformat()
    return key, parsed


def redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.lower() in _SECRET_KEYS else redact_mapping(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    return value


def _validate(config: RunConfig) -> None:
    if config.seed < 0:
        raise ConfigError("seed must be non-negative")
    if config.training.total_steps <= 0 or config.training.n_envs <= 0:
        raise ConfigError("training total_steps and n_envs must be positive")
    if config.checkpoint.every_steps <= 0:
        raise ConfigError("checkpoint every_steps must be positive")
    if config.evaluation.episodes <= 0 or not config.evaluation.seeds:
        raise ConfigError("evaluation requires positive episodes and at least one seed")
    if config.rendering.frames < 10 or config.rendering.fps <= 0:
        raise ConfigError("rendering requires at least 10 frames and a positive fps")
    if config.success.kind == "mean_reward" and config.success.threshold is None:
        raise ConfigError("mean_reward success requires threshold")
    if config.success.kind == "locomotion" and config.success.min_velocity is None:
        raise ConfigError("locomotion success requires min_velocity")
    if config.success.kind == "locomotion" and (
        config.success.target_velocity <= 0
        or float(config.success.min_velocity or 0) > config.success.target_velocity
    ):
        raise ConfigError(
            "locomotion target_velocity must be positive and at least min_velocity"
        )
    if config.backend == "sb3" and config.success.kind != "mean_reward":
        raise ConfigError("SB3 configs currently require mean_reward success")
    if config.backend == "mjx" and config.success.kind != "locomotion":
        raise ConfigError("MJX configs currently require locomotion success")
    if config.backend == "mjx":
        playground_overrides = config.training.hyperparameters.get(
            "playground_config_overrides"
        )
        if playground_overrides is not None:
            if not isinstance(playground_overrides, dict):
                raise ConfigError("MJX playground_config_overrides must be a mapping")
            unknown_overrides = sorted(
                set(playground_overrides) - {"push_config.enable"}
            )
            if unknown_overrides:
                raise ConfigError(
                    "unsupported MJX Playground environment override(s): "
                    + ", ".join(unknown_overrides)
                )
            if not isinstance(playground_overrides.get("push_config.enable"), bool):
                raise ConfigError(
                    "MJX push_config.enable environment override must be boolean"
                )
        batch_size = config.training.hyperparameters.get("batch_size")
        num_minibatches = config.training.hyperparameters.get("num_minibatches")
        if batch_size is not None and num_minibatches is not None:
            if (
                not isinstance(batch_size, int)
                or isinstance(batch_size, bool)
                or batch_size <= 0
                or not isinstance(num_minibatches, int)
                or isinstance(num_minibatches, bool)
                or num_minibatches <= 0
            ):
                raise ConfigError("MJX batch_size and num_minibatches must be positive integers")
            if batch_size * num_minibatches % config.training.n_envs != 0:
                raise ConfigError(
                    "MJX batch_size multiplied by num_minibatches must be divisible by n_envs"
                )
    if config.storage.mode == "s3" and not config.storage.bucket:
        raise ConfigError("S3 storage mode requires bucket")
    validate_prefix(config.storage.prefix)


def load_config(path: str | Path, overrides: dict[str, Any] | None = None) -> RunConfig:
    source = Path(path)
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be a mapping")
    raw = dict(raw)
    for dotted_key, value in sorted((overrides or {}).items()):
        parts = dotted_key.split(".")
        if len(parts) == 1:
            if parts[0] not in {"backend", "environment", "seed"}:
                raise ConfigError(f"unsupported override: {dotted_key}")
            raw[parts[0]] = value
        elif len(parts) == 2 and parts[0] in _SECTIONS:
            if not isinstance(raw.get(parts[0], {}), dict):
                raise ConfigError(f"cannot override non-mapping section: {parts[0]}")
            raw.setdefault(parts[0], {})[parts[1]] = value
        else:
            raise ConfigError(f"unsupported override: {dotted_key}")

    allowed_root = {"backend", "environment", "seed", *_SECTIONS}
    unknown = sorted(set(raw) - allowed_root)
    if unknown:
        raise ConfigError(f"unknown root setting(s): {', '.join(unknown)}")
    required_root = {
        "backend",
        "environment",
        "seed",
        "training",
        "checkpoint",
        "evaluation",
        "success",
    }
    missing = sorted(required_root - set(raw))
    if missing:
        raise ConfigError(f"missing root setting(s): {', '.join(missing)}")

    backend = raw["backend"]
    if backend not in {"sb3", "mjx"}:
        raise ConfigError("backend must be 'sb3' or 'mjx'")
    sections = {name: _construct(cls, raw.get(name, {}), name) for name, cls in _SECTIONS.items()}
    config = RunConfig(
        backend=backend,
        environment=str(raw["environment"]),
        seed=int(raw["seed"]),
        **sections,
    )
    _validate(config)
    return config
