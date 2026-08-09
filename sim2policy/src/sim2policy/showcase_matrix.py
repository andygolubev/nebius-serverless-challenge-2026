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

from .locomotion_gate import MIN_GATE_PASS_PROBABILITY, gate_pass_probability


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
                raise MatrixError(
                    f"examples.{name}.acceptance.{level}.no_fall is implicit; declare "
                    "required_horizons and assumed_reliability so the gate's pass "
                    "probability can be checked"
                )
            _number(threshold, f"examples.{name}.acceptance.{level}.{criterion}")
        required = criteria.get("required_horizons")
        episodes = criteria.get("episodes")
        if backend == "mjx":
            if required is None or episodes is None:
                raise MatrixError(
                    f"examples.{name}.acceptance.{level} requires episodes and "
                    "required_horizons"
                )
            if int(required) > int(episodes):
                raise MatrixError(
                    f"examples.{name}.acceptance.{level}.required_horizons exceeds episodes"
                )
            reliability = criteria.get("assumed_reliability")
            if reliability is None:
                raise MatrixError(
                    f"examples.{name}.acceptance.{level} must declare assumed_reliability"
                )
            # Rollouts are sampled, so a gate can be unreachable in practice even
            # for a policy that is good enough. Refuse to fund one that a policy
            # meeting the assumed reliability would fail more often than not.
            chance = gate_pass_probability(
                int(episodes), int(required), float(reliability)
            )
            if chance < MIN_GATE_PASS_PROBABILITY:
                raise MatrixError(
                    f"examples.{name}.acceptance.{level} passes only {chance:.1%} of the "
                    f"time for a policy at {float(reliability):.2f} per-episode "
                    f"reliability ({required}/{episodes}); below the required "
                    f"{MIN_GATE_PASS_PROBABILITY:.0%} floor"
                )
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
        _only(curriculum, {"flat_config", "rough_config", "flat_environment", "rough_environment", "flat_command", "rough_command", "flat_nominal_steps", "flat_effective_steps", "candidate_every_steps", "pushes_enabled", "authorization", "diagnostic", "pilot", "full"}, "examples.g1.curriculum")
        if curriculum.get("flat_config") != "configs/g1_forward_flat_mjx.yaml" or curriculum.get("rough_config") != "configs/g1_forward_rough_mjx.yaml":
            raise MatrixError("G1 curriculum config identities are invalid")
        if curriculum.get("flat_environment") != "G1ForwardFlatTerrain" or curriculum.get("rough_environment") != "G1ForwardRoughTerrain":
            raise MatrixError("G1 curriculum environment identities are invalid")
        if curriculum.get("flat_command") != [1.0, 0.0, 0.0] or curriculum.get("rough_command") != [0.8, 0.0, 0.0]:
            raise MatrixError("G1 curriculum command contract is invalid")
        if curriculum.get("flat_nominal_steps") != 200_000_000 or curriculum.get("flat_effective_steps") != 199_229_440:
            raise MatrixError("G1 curriculum flat step contract is invalid")
        if curriculum.get("candidate_every_steps") != cadence or curriculum.get("pushes_enabled") is not False:
            raise MatrixError("G1 curriculum cadence or push setting is invalid")
        authorization = _mapping(curriculum.get("authorization"), "examples.g1.curriculum.authorization")
        _only(authorization, {"mode", "campaign_id", "allowed_jobs", "retries_allowed", "extensions_allowed", "runtime_overrides_allowed", "superseded_sweep_run_id", "superseded_sweep_job_id", "superseded_result_campaign_id", "superseded_result_job_id", "pilot_required"}, "examples.g1.curriculum.authorization")
        if authorization != {
            "mode": "user_reviewed_rough_08_full_v2",
            "campaign_id": "gallery-g1-rough08-full-20260803-01",
            "allowed_jobs": 1,
            "retries_allowed": 0,
            "extensions_allowed": False,
            "runtime_overrides_allowed": False,
            "superseded_sweep_run_id": "sweep-g1-c1a522b-20260802-01",
            "superseded_sweep_job_id": "aijob-e00c8fwyh15gy7qggk",
            "superseded_result_campaign_id": "gallery-g1-direct-full-20260803-01",
            "superseded_result_job_id": "aijob-e00pc60w55v89z6t5v",
            "pilot_required": False,
        }:
            raise MatrixError("G1 rough-0.8 authorization contract is invalid")
        diagnostic = _mapping(curriculum.get("diagnostic"), "examples.g1.curriculum.diagnostic")
        _only(diagnostic, {"source_run_id", "source_environment", "environments", "episodes_per_seed", "flat_required_horizons", "min_velocity", "ranking"}, "examples.g1.curriculum.diagnostic")
        if (
            diagnostic.get("source_run_id")
            != "showcase-gallery-g1-20260801-16-g1-s0-flat"
            or diagnostic.get("source_environment") != "G1JoystickFlatTerrain"
            or diagnostic.get("environments") != ["G1ForwardFlatTerrain", "G1ForwardRoughTerrain"]
            or diagnostic.get("episodes_per_seed") != 4
            or diagnostic.get("flat_required_horizons") != 20
            or diagnostic.get("min_velocity") != 0.4
            or diagnostic.get("ranking") != ["rough_horizon_count", "rough_mean_episode_length", "rough_min_velocity", "rough_mean_velocity", "rough_mean_reward", "earlier_checkpoint"]
        ):
            raise MatrixError("G1 diagnostic sweep contract is invalid")
        pilot = _mapping(curriculum.get("pilot"), "examples.g1.curriculum.pilot")
        _only(pilot, {"step_ceiling", "effective_steps", "timeout_minutes", "seed", "required_horizons", "episodes", "mean_episode_length", "min_velocity", "max_nan_terminations"}, "examples.g1.curriculum.pilot")
        if pilot != {
            "step_ceiling": 50_000_000,
            "effective_steps": 46_202_880,
            "timeout_minutes": 90,
            "seed": 0,
            "required_horizons": 5,
            "episodes": 10,
            "mean_episode_length": 900,
            "min_velocity": 0.4,
            "max_nan_terminations": 0,
        }:
            raise MatrixError("G1 pilot contract is invalid")
        full = _mapping(curriculum.get("full"), "examples.g1.curriculum.full")
        _only(full, {"total_step_ceiling", "rough_effective_steps", "timeout_minutes", "seed", "flat_gate_episodes", "flat_required_horizons", "flat_min_velocity", "extension_steps"}, "examples.g1.curriculum.full")
        if full != {
            "total_step_ceiling": 450_000_000,
            "rough_effective_steps": 250_511_360,
            "timeout_minutes": 300,
            "seed": 0,
            "flat_gate_episodes": 10,
            "flat_required_horizons": 9,
            "flat_min_velocity": 0.4,
            "extension_steps": None,
        }:
            raise MatrixError("G1 full campaign contract is invalid")
    elif "curriculum" in value:
        raise MatrixError(f"examples.{name} cannot declare a curriculum")
    return value


def load_matrix(path: str | Path) -> CampaignMatrix:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "matrix")
    _only(root, {"schema_version", "campaign", "examples"}, "matrix")
    if root.get("schema_version") != 2:
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
    normalized = {"schema_version": 2, "campaign": campaign, "examples": {name: _validate_card(name, examples[name]) for name in EXAMPLE_ORDER}}
    return CampaignMatrix(normalized=normalized, digest=normalized_digest(normalized))
