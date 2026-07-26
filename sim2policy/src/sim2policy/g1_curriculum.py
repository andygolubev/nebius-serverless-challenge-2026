"""Fixed-budget G1 flat-to-rough curriculum contracts.

This module contains the numerical gate and provenance logic used by the Nebius
job wrapper.  It cannot create a second seed, change reward settings, or exceed
the reviewed 450M effective-step ceiling.
"""

# ruff: noqa: E501, I001

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


FLAT_ENVIRONMENT = "G1JoystickFlatTerrain"
ROUGH_ENVIRONMENT = "G1JoystickRoughTerrain"
FLAT_GATES = (100_000_000, 150_000_000, 200_000_000)
TOTAL_STEPS = 450_000_000
HORIZON = 1_000


class CurriculumError(ValueError):
    pass


@dataclass(frozen=True)
class FlatGateResult:
    step: int
    passed: bool
    no_fall_count: int
    min_velocity: float
    complete_horizon_count: int


def flat_gate_result(
    step: int, episodes: Iterable[dict[str, Any]], *, min_velocity: float = 0.4
) -> FlatGateResult:
    if step not in FLAT_GATES:
        raise CurriculumError("flat result was not measured at a reviewed gate")
    values = tuple(episodes)
    if not values:
        raise CurriculumError("flat prerequisite has no deterministic episodes")
    no_fall = [not bool(item.get("fell", True)) for item in values]
    full_horizon = [int(item.get("length", 0)) >= HORIZON for item in values]
    velocities = [float(item.get("mean_velocity", 0.0)) for item in values]
    # Standing and reward-only improvement cannot pass: every selection episode
    # must move under the declared command for the full rollout without falling.
    passed = all(no_fall) and all(full_horizon) and min(velocities) >= min_velocity
    return FlatGateResult(
        step=step,
        passed=passed,
        no_fall_count=sum(no_fall),
        min_velocity=min(velocities),
        complete_horizon_count=sum(full_horizon),
    )


def selected_flat_gate(results: Iterable[FlatGateResult]) -> FlatGateResult | None:
    indexed = {item.step: item for item in results}
    if set(indexed) - set(FLAT_GATES):
        raise CurriculumError("unreviewed flat gate supplied")
    for step in FLAT_GATES:
        result = indexed.get(step)
        if result is not None and result.passed:
            return result
    return None


def rough_budget(selected_flat_step: int) -> int:
    if selected_flat_step not in FLAT_GATES:
        raise CurriculumError("rough resume requires one selected reviewed flat gate")
    remaining = TOTAL_STEPS - selected_flat_step
    if remaining <= 0:
        raise CurriculumError("G1 curriculum would exceed its total-step ceiling")
    return remaining


def provenance_chain(
    *,
    matrix_digest: str,
    image_digest: str,
    flat_config_digest: str,
    rough_config_digest: str,
    flat_checkpoint_digest: str,
    rough_checkpoint_digest: str | None,
    selected_flat_step: int,
    phase_outcomes: dict[str, Any],
    rough_effective_steps: int | None = None,
    phase_timings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    budget = rough_budget(selected_flat_step)
    if rough_effective_steps is not None and rough_effective_steps > budget:
        raise CurriculumError("rough phase measured more steps than its remaining budget")
    measured_total = selected_flat_step + (rough_effective_steps or 0)
    if measured_total > TOTAL_STEPS:
        raise CurriculumError("G1 curriculum measured more steps than its 450M ceiling")
    evidence = {
        "schema_version": 1,
        "matrix_digest": matrix_digest,
        "image_digest": image_digest,
        "flat": {
            "environment": FLAT_ENVIRONMENT,
            "config_digest": flat_config_digest,
            "output_checkpoint_digest": flat_checkpoint_digest,
            "effective_steps": selected_flat_step,
            "pushes_enabled": False,
            "outcome": phase_outcomes.get("flat"),
            "timing_seconds": (phase_timings or {}).get("flat"),
        },
        "rough": {
            "environment": ROUGH_ENVIRONMENT,
            "config_digest": rough_config_digest,
            "input_checkpoint_digest": flat_checkpoint_digest,
            "output_checkpoint_digest": rough_checkpoint_digest,
            "budget_effective_steps": budget,
            "effective_steps": rough_effective_steps,
            "pushes_enabled": False,
            "outcome": phase_outcomes.get("rough"),
            "timing_seconds": (phase_timings or {}).get("rough"),
        },
        "effective_total_steps": TOTAL_STEPS,
        "measured_total_steps": measured_total,
    }
    evidence["provenance_digest"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return evidence
