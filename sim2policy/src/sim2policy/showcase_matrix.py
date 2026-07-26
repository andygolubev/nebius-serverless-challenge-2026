"""Strict, versioned input contract for the result-first showcase campaign."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class MatrixError(ValueError):
    """Raised when a campaign matrix is incomplete, mutable, or inconsistent."""


EXAMPLE_ORDER = ("reacher", "halfcheetah", "ant", "hopper", "walker2d", "go1", "g1")
_EXAMPLE_IDS = {
    "reacher": "reacher-target",
    "halfcheetah": "halfcheetah-sprint",
    "ant": "ant-explorer",
    "hopper": "hopper-balance",
    "walker2d": "walker2d-stride",
    "go1": "go1-walker",
    "g1": "g1-rough-terrain",
}
_TAG_TEMPLATE = re.compile(r"^(?:sb3|mjx)-\{git_sha\}$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def normalized_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MatrixError(f"{name} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _only(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise MatrixError(f"{name} has unknown fields: {', '.join(sorted(unknown))}")


def _positive(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MatrixError(f"{name} must be a positive integer")
    return int(value)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MatrixError(f"{name} must be numeric")
    return float(value)


@dataclass(frozen=True)
class CampaignMatrix:
    normalized: dict[str, Any]
    digest: str

    @property
    def examples(self) -> dict[str, dict[str, Any]]:
        examples = self.normalized["examples"]
        if not isinstance(examples, dict):  # defensive; `load_matrix` already validates this
            raise MatrixError("normalized matrix examples are invalid")
        return examples

    @property
    def campaign(self) -> dict[str, Any]:
        campaign = self.normalized["campaign"]
        if not isinstance(campaign, dict):  # defensive; `load_matrix` already validates this
            raise MatrixError("normalized matrix campaign is invalid")
        return campaign

    def card(self, example: str) -> dict[str, Any]:
        try:
            return self.examples[example]
        except KeyError as exc:
            raise MatrixError(f"unknown showcase example: {example}") from exc


def _validate_card(name: str, card: Any) -> dict[str, Any]:
    value = _mapping(card, f"examples.{name}")
    _only(
        value,
        {
            "gallery_example_id", "backend", "config", "image", "seeds", "base_steps",
            "extension_steps", "checkpoint_every_steps", "hardware", "acceptance", "ranking",
            "curriculum",
        },
        f"examples.{name}",
    )
    if value.get("gallery_example_id") != _EXAMPLE_IDS[name]:
        raise MatrixError(f"examples.{name} must use its server-owned gallery example ID")
    backend = value.get("backend")
    if backend not in {"sb3", "mjx"}:
        raise MatrixError(f"examples.{name}.backend is invalid")
    if not isinstance(value.get("config"), str) or not value["config"].startswith("configs/"):
        raise MatrixError(f"examples.{name}.config must be a repository config path")
    image = _mapping(value.get("image"), f"examples.{name}.image")
    _only(image, {"runtime", "tag_template"}, f"examples.{name}.image")
    if image.get("runtime") != backend or not isinstance(image.get("tag_template"), str):
        raise MatrixError(f"examples.{name}.image does not match its backend")
    if not _TAG_TEMPLATE.fullmatch(image["tag_template"]):
        raise MatrixError(f"examples.{name}.image must use immutable git-SHA tag template")
    seeds = value.get("seeds")
    if not isinstance(seeds, list) or not seeds or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds):
        raise MatrixError(f"examples.{name}.seeds must be integer seeds")
    if len(set(seeds)) != len(seeds):
        raise MatrixError(f"examples.{name}.seeds must be unique")
    base = _positive(value.get("base_steps"), f"examples.{name}.base_steps")
    extension = value.get("extension_steps")
    if name == "g1":
        if extension is not None or len(seeds) != 1 or seeds != [0] or base != 450_000_000:
            raise MatrixError("G1 must be exactly one seed-0 450M run with no extension")
    else:
        if seeds != [0, 7, 42] or not isinstance(extension, int) or extension <= base:
            raise MatrixError(f"examples.{name} must have its single declared extension")
    cadence = _positive(value.get("checkpoint_every_steps"), f"examples.{name}.checkpoint_every_steps")
    hardware = _mapping(value.get("hardware"), f"examples.{name}.hardware")
    _only(hardware, {"platform", "preset", "disk_gib", "timeout_minutes", "preemptible"}, f"examples.{name}.hardware")
    if hardware.get("preemptible") is not False:
        raise MatrixError(f"examples.{name} must be non-preemptible")
    _positive(hardware.get("disk_gib"), f"examples.{name}.hardware.disk_gib")
    _positive(hardware.get("timeout_minutes"), f"examples.{name}.hardware.timeout_minutes")
    expected_hardware = ("cpu-d3", "8vcpu-32gb") if backend == "sb3" else ("gpu-h100-sxm", "1gpu-16vcpu-200gb")
    if (hardware.get("platform"), hardware.get("preset")) != expected_hardware:
        raise MatrixError(f"examples.{name} has the wrong hardware for {backend}")
    acceptance = _mapping(value.get("acceptance"), f"examples.{name}.acceptance")
    _only(acceptance, {"hard", "preferred"}, f"examples.{name}.acceptance")
    for level in ("hard", "preferred"):
        criteria = _mapping(acceptance.get(level), f"examples.{name}.acceptance.{level}")
        if not criteria:
            raise MatrixError(f"examples.{name}.acceptance.{level} is required")
        for criterion, threshold in criteria.items():
            if criterion == "no_fall":
                if threshold is not True:
                    raise MatrixError(f"examples.{name}.acceptance.{level}.no_fall must be true")
            else:
                _number(threshold, f"examples.{name}.acceptance.{level}.{criterion}")
    ranking = _mapping(value.get("ranking"), f"examples.{name}.ranking")
    kind = ranking.get("kind")
    if kind != ("mean_reward" if backend == "sb3" else "locomotion"):
        raise MatrixError(f"examples.{name}.ranking is incompatible with backend")
    if backend == "mjx" and ranking.get("fields") != [
        "no_fall_count",
        "min_velocity",
        "mean_episode_length",
        "mean_velocity",
        "mean_reward",
        "earlier_checkpoint",
    ]:
        raise MatrixError(f"examples.{name}.ranking must use the fixed locomotion order")
    if name == "g1":
        curriculum = _mapping(value.get("curriculum"), "examples.g1.curriculum")
        _only(curriculum, {"flat_config", "rough_config", "flat_environment", "rough_environment", "flat_gates", "candidate_every_steps", "pushes_enabled"}, "examples.g1.curriculum")
        if curriculum.get("flat_config") != "configs/g1_flat_mjx.yaml" or curriculum.get("rough_config") != "configs/g1_mjx.yaml":
            raise MatrixError("G1 curriculum config identities are invalid")
        if curriculum.get("flat_environment") != "G1JoystickFlatTerrain" or curriculum.get("rough_environment") != "G1JoystickRoughTerrain":
            raise MatrixError("G1 curriculum environment identities are invalid")
        if curriculum.get("flat_gates") != [100_000_000, 150_000_000, 200_000_000]:
            raise MatrixError("G1 curriculum flat gates are invalid")
        if curriculum.get("candidate_every_steps") != cadence or curriculum.get("pushes_enabled") is not False:
            raise MatrixError("G1 curriculum cadence or push setting is invalid")
    elif "curriculum" in value:
        raise MatrixError(f"examples.{name} cannot declare a curriculum")
    return value


def load_matrix(path: str | Path) -> CampaignMatrix:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "matrix")
    _only(root, {"schema_version", "campaign", "examples"}, "matrix")
    if root.get("schema_version") != 1:
        raise MatrixError("unsupported showcase matrix schema version")
    campaign = _mapping(root.get("campaign"), "campaign")
    _only(campaign, {"execution_location", "max_active_jobs", "selection", "final"}, "campaign")
    if campaign.get("execution_location") != "nebius" or campaign.get("max_active_jobs") != 1:
        raise MatrixError("campaign execution location or active-job limit is invalid")
    for role, expected_seeds, expected_episodes in (
        ("selection", [101, 151, 211, 271, 331], 2),
        ("final", [0, 1, 2, 3, 4], 4),
    ):
        item = _mapping(campaign.get(role), f"campaign.{role}")
        _only(item, {"seeds", "episodes_per_seed"}, f"campaign.{role}")
        if item.get("seeds") != expected_seeds or item.get("episodes_per_seed") != expected_episodes:
            raise MatrixError(f"campaign.{role} does not match the reviewed deterministic schedule")
    if set(campaign["selection"]["seeds"]) & set(campaign["final"]["seeds"]):
        raise MatrixError("selection and final seed sets overlap")
    examples = _mapping(root.get("examples"), "examples")
    if tuple(examples) != EXAMPLE_ORDER or set(examples) != set(EXAMPLE_ORDER):
        raise MatrixError("matrix example IDs must be the exact ordered showcase set")
    normalized = {"schema_version": 1, "campaign": campaign, "examples": {name: _validate_card(name, examples[name]) for name in EXAMPLE_ORDER}}
    return CampaignMatrix(normalized=normalized, digest=normalized_digest(normalized))
