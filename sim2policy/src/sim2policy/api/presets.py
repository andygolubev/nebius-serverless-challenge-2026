"""Allowlisted demo training presets.

The catalog (``configs/training_presets.yaml``) is the allowlist: only presets
defined and enabled there are valid, and a preset resolves to the project's
existing :class:`RunConfig` schema. No user-supplied environment IDs, images,
commands, code, or reward functions are ever accepted.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sim2policy.config import RunConfig, load_config

# Nebius duration string, e.g. "1h" or "2h30m". Mirrors jobs/submit.sh validation.
_DURATION_PATTERN = __import__("re").compile(r"^[0-9]+(h|m|s)([0-9]+(m|s))?$")


class PresetError(ValueError):
    """Raised when the preset catalog is malformed or a request is invalid."""


@dataclass(frozen=True)
class SafeParam:
    name: str
    type: str  # "int" | "bool"
    default: Any
    min: int | None = None
    max: int | None = None

    def coerce(self, value: Any) -> Any:
        if self.type == "bool":
            if not isinstance(value, bool):
                raise PresetError(f"parameter '{self.name}' must be a boolean")
            return value
        if self.type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise PresetError(f"parameter '{self.name}' must be an integer")
            if self.min is not None and value < self.min:
                raise PresetError(f"parameter '{self.name}' must be >= {self.min}")
            if self.max is not None and value > self.max:
                raise PresetError(f"parameter '{self.name}' must be <= {self.max}")
            return value
        raise PresetError(f"unsupported safe-param type: {self.type}")  # pragma: no cover

    def describe(self) -> dict[str, Any]:
        info: dict[str, Any] = {"type": self.type, "default": self.default}
        if self.min is not None:
            info["min"] = self.min
        if self.max is not None:
            info["max"] = self.max
        return info


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    enabled: bool
    backend: str
    environment: str
    algorithm: str
    base_config: str
    max_duration: str
    overrides: dict[str, Any] = field(default_factory=dict)
    max_total_steps: int | None = None
    expected_artifacts: list[str] = field(default_factory=list)
    safe_params: dict[str, SafeParam] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description.strip(),
            "backend": self.backend,
            "environment": self.environment,
            "algorithm": self.algorithm,
            "max_duration": self.max_duration,
            "max_total_steps": self.max_total_steps,
            "expected_artifacts": list(self.expected_artifacts),
            "safe_params": {name: param.describe() for name, param in self.safe_params.items()},
        }


@dataclass(frozen=True)
class ResolvedRun:
    preset: str
    backend: str
    config: RunConfig
    safe_params: dict[str, Any]
    max_duration: str
    config_path: str


def _parse_safe_param(name: str, raw: Any) -> SafeParam:
    if not isinstance(raw, dict) or "type" not in raw or "default" not in raw:
        raise PresetError(f"safe param '{name}' must declare type and default")
    return SafeParam(
        name=name,
        type=str(raw["type"]),
        default=raw["default"],
        min=raw.get("min"),
        max=raw.get("max"),
    )


def _parse_preset(name: str, raw: Any) -> Preset:
    if not isinstance(raw, dict):
        raise PresetError(f"preset '{name}' must be a mapping")
    required = {"backend", "environment", "base_config"}
    missing = sorted(required - set(raw))
    if missing:
        raise PresetError(f"preset '{name}' missing setting(s): {', '.join(missing)}")
    limits = raw.get("limits") or {}
    if not isinstance(limits, dict):
        raise PresetError(f"preset '{name}' limits must be a mapping")
    max_duration = str(limits.get("max_duration", "1h"))
    if not _DURATION_PATTERN.fullmatch(max_duration):
        raise PresetError(f"preset '{name}' max_duration is not a valid Nebius duration")
    overrides = raw.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise PresetError(f"preset '{name}' overrides must be a mapping")
    safe_params = {
        param_name: _parse_safe_param(param_name, param_raw)
        for param_name, param_raw in (raw.get("safe_params") or {}).items()
    }
    return Preset(
        name=name,
        description=str(raw.get("description", "")),
        enabled=bool(raw.get("enabled", True)),
        backend=str(raw["backend"]),
        environment=str(raw["environment"]),
        algorithm=str(raw.get("algorithm", "PPO")),
        base_config=str(raw["base_config"]),
        max_duration=max_duration,
        overrides=dict(overrides),
        max_total_steps=limits.get("max_total_steps"),
        expected_artifacts=list(raw.get("expected_artifacts") or []),
        safe_params=safe_params,
    )


class PresetCatalog:
    """In-memory view of the allowlisted preset catalog."""

    def __init__(self, presets: dict[str, Preset], *, root: Path) -> None:
        self._presets = presets
        self._root = root

    @classmethod
    def load(cls, path: str | Path) -> PresetCatalog:
        catalog_path = Path(path)
        if not catalog_path.is_file():
            raise PresetError(f"preset catalog not found: {catalog_path}")
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("presets"), dict):
            raise PresetError("preset catalog must contain a 'presets' mapping")
        presets: dict[str, Preset] = {}
        for name, preset_raw in raw["presets"].items():
            if name in presets:
                raise PresetError(f"duplicate preset name: {name}")
            presets[name] = _parse_preset(str(name), preset_raw)
        if not presets:
            raise PresetError("preset catalog is empty")
        # configs/training_presets.yaml -> project root is two levels up.
        root = catalog_path.resolve().parent.parent
        return cls(presets, root=root)

    def names(self, *, include_disabled: bool = False) -> list[str]:
        return [
            name
            for name, preset in self._presets.items()
            if include_disabled or preset.enabled
        ]

    def list_enabled(self) -> list[Preset]:
        return [preset for preset in self._presets.values() if preset.enabled]

    def get(self, name: str) -> Preset:
        preset = self._presets.get(name)
        if preset is None or not preset.enabled:
            raise PresetError(f"unknown or disabled preset: {name}")
        return preset

    def resolve(self, name: str, params: dict[str, Any] | None = None) -> ResolvedRun:
        preset = self.get(name)
        supplied = dict(params or {})
        unknown = sorted(set(supplied) - set(preset.safe_params))
        if unknown:
            raise PresetError(f"unsupported parameter(s) for '{name}': {', '.join(unknown)}")

        resolved_params: dict[str, Any] = {}
        config_overrides: dict[str, Any] = dict(preset.overrides)
        for param_name, param in preset.safe_params.items():
            value = (
                param.coerce(supplied[param_name])
                if param_name in supplied
                else param.default
            )
            resolved_params[param_name] = value
            if param_name == "seed":
                config_overrides["seed"] = value

        base = self._root / preset.base_config
        config = load_config(base, config_overrides)
        if config.backend != preset.backend:
            raise PresetError(
                f"preset '{name}' backend {preset.backend} does not match base config"
            )
        config = self._enforce_limits(preset, config)
        return ResolvedRun(
            preset=name,
            backend=preset.backend,
            config=config,
            safe_params=resolved_params,
            max_duration=preset.max_duration,
            config_path=preset.base_config,
        )

    @staticmethod
    def _enforce_limits(preset: Preset, config: RunConfig) -> RunConfig:
        if preset.max_total_steps is not None and (
            config.training.total_steps > preset.max_total_steps
        ):
            capped = dataclasses.replace(config.training, total_steps=preset.max_total_steps)
            config = dataclasses.replace(config, training=capped)
        return config


def default_catalog_path(root: str | Path | None = None) -> Path:
    """Locate ``configs/training_presets.yaml`` relative to the project root."""
    base = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    return base / "configs" / "training_presets.yaml"
