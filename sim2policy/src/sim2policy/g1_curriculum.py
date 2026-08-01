"""Fixed-budget G1 flat-to-rough curriculum contracts.

This module contains the numerical gate and provenance logic used by the Nebius
job wrapper.  It cannot create a second seed, change reward settings, or exceed
the reviewed 450M effective-step ceiling.
"""

# ruff: noqa: E501, I001

from __future__ import annotations

import hashlib
import json
import math
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


def rough_budget(
    selected_flat_step: int,
    *,
    checkpoint_effective_step: int | None = None,
    flat_trained_steps: int | None = None,
) -> int:
    if selected_flat_step not in FLAT_GATES:
        raise CurriculumError("rough resume requires one selected reviewed flat gate")
    effective_step = (
        selected_flat_step
        if checkpoint_effective_step is None
        else checkpoint_effective_step
    )
    if effective_step <= 0 or effective_step > selected_flat_step:
        raise CurriculumError(
            "selected flat checkpoint must be positive and no later than its reviewed gate"
        )
    spent = effective_step if flat_trained_steps is None else flat_trained_steps
    if spent < effective_step:
        raise CurriculumError("flat training spend cannot precede the selected checkpoint")
    if spent >= TOTAL_STEPS:
        raise CurriculumError("flat training consumed the total G1 step ceiling")
    remaining = TOTAL_STEPS - spent
    if remaining <= 0:
        raise CurriculumError("G1 curriculum would exceed its total-step ceiling")
    return remaining


def bounded_mjx_phase_steps(
    budget: int,
    *,
    checkpoint_every_steps: int,
    n_envs: int,
    unroll_length: int,
) -> int:
    """Return an MJX request whose executed PPO steps cannot exceed ``budget``.

    Brax divides a run into ``num_evals - 1`` training epochs and rounds every
    epoch up to a whole ``n_envs * unroll_length`` batch.  Passing a nominal
    200M/250M request therefore executed 200,540,160/250,675,200 steps in the
    first production curriculum.  Aligning the request to the combined epoch
    quantum prevents that upstream rounding from violating the reviewed 450M
    effective-step ceiling.
    """
    if min(budget, checkpoint_every_steps, n_envs, unroll_length) <= 0:
        raise CurriculumError("MJX phase budget and batch dimensions must be positive")
    intervals = max(1, math.ceil(budget / checkpoint_every_steps))
    while True:
        epoch_quantum = n_envs * unroll_length * intervals
        bounded = (budget // epoch_quantum) * epoch_quantum
        if bounded <= 0:
            raise CurriculumError("MJX phase budget is smaller than one training epoch")
        adjusted_intervals = max(1, math.ceil(bounded / checkpoint_every_steps))
        if adjusted_intervals == intervals:
            return bounded
        intervals = adjusted_intervals


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
    flat_effective_steps: int | None = None,
    flat_trained_steps: int | None = None,
    rough_effective_steps: int | None = None,
    rough_requested_steps: int | None = None,
    phase_timings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_flat = flat_effective_steps or selected_flat_step
    measured_flat = flat_trained_steps or selected_flat
    budget = rough_budget(
        selected_flat_step,
        checkpoint_effective_step=selected_flat,
        flat_trained_steps=measured_flat,
    )
    if rough_requested_steps is not None and rough_requested_steps > budget:
        raise CurriculumError("rough phase request exceeds its remaining budget")
    if rough_effective_steps is not None and rough_effective_steps > budget:
        raise CurriculumError("rough phase measured more steps than its remaining budget")
    measured_total = measured_flat + (rough_effective_steps or 0)
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
            "gate_step": selected_flat_step,
            "effective_steps": selected_flat,
            "trained_effective_steps": measured_flat,
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
            "requested_effective_steps": rough_requested_steps,
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
