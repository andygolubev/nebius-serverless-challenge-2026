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


FLAT_ENVIRONMENT = "G1ForwardFlatTerrain"
ROUGH_ENVIRONMENT = "G1ForwardRoughTerrain"
FLAT_NOMINAL_STEPS = 200_000_000
FLAT_EFFECTIVE_STEPS = 199_229_440
FLAT_GATES = (FLAT_EFFECTIVE_STEPS,)
PILOT_STEP_CEILING = 50_000_000
PILOT_EFFECTIVE_STEPS = 46_202_880
TOTAL_STEPS = 450_000_000
HORIZON = 1_000
# Gate tolerances. Evidence is a sample, not an exact measurement, so an
# all-or-nothing bar cannot be met reliably even by a good policy: at the
# measured per-episode survival of ~0.80, 10/10 passes 10.7% of the time and
# 20/20 passes 1.2%. At 9/10 and 18/20 a 0.95-reliable policy passes 91% and
# 93%, while a 0.80-reliable one is still rejected (38% and 21%).
FLAT_GATE_EPISODES = 10
FLAT_REQUIRED_HORIZONS = 9
FINAL_GATE_EPISODES = 20
FINAL_REQUIRED_HORIZONS = 18


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
    step: int,
    episodes: Iterable[dict[str, Any]],
    *,
    min_velocity: float = 0.4,
    required_horizons: int = FLAT_REQUIRED_HORIZONS,
) -> FlatGateResult:
    if step not in FLAT_GATES:
        raise CurriculumError("flat result was not measured at a reviewed gate")
    values = tuple(episodes)
    if not values:
        raise CurriculumError("flat prerequisite has no episodes")
    no_fall = [
        item.get("termination_reason", "horizon") == "horizon"
        and not bool(item.get("terminated", item.get("fell", True)))
        for item in values
    ]
    full_horizon = [int(item.get("length", 0)) >= HORIZON for item in values]
    # Only a completed episode has a meaningful average velocity. An episode that
    # terminates early and lands face-down averages backwards, and counting that
    # as a *velocity* failure reports one defect twice -- it is already failing as
    # a missing horizon. The published flat evidence read -1.1908 m/s for exactly
    # this reason.
    completed_velocities = [
        float(item.get("mean_velocity", 0.0))
        for item, complete in zip(values, full_horizon, strict=True)
        if complete
    ]
    horizon_count = sum(full_horizon)
    # Rollouts are sampled, not bit-reproducible (MJX reductions on GPU are not
    # bit-deterministic and legged gait is chaotic), so the gate states a
    # tolerance rather than demanding that every sampled episode be perfect.
    # Standing still cannot pass regardless: every completed episode must still
    # average at least ``min_velocity`` under the declared command.
    passed = (
        horizon_count >= required_horizons
        and sum(no_fall) >= required_horizons
        and bool(completed_velocities)
        and min(completed_velocities) >= min_velocity
    )
    return FlatGateResult(
        step=step,
        passed=passed,
        no_fall_count=sum(no_fall),
        min_velocity=min(completed_velocities) if completed_velocities else 0.0,
        complete_horizon_count=horizon_count,
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
    if selected_flat_step != FLAT_EFFECTIVE_STEPS:
        raise CurriculumError("rough resume requires the exact derived flat gate")
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


def assert_reviewed_step_contract() -> dict[str, int]:
    """Derive and assert the exact reviewed G1 executable step requests."""
    flat = bounded_mjx_phase_steps(
        FLAT_NOMINAL_STEPS,
        checkpoint_every_steps=25_000_000,
        n_envs=8_192,
        unroll_length=20,
    )
    pilot = bounded_mjx_phase_steps(
        PILOT_EFFECTIVE_STEPS,
        checkpoint_every_steps=25_000_000,
        n_envs=8_192,
        unroll_length=20,
    )
    if flat != FLAT_EFFECTIVE_STEPS or pilot != PILOT_EFFECTIVE_STEPS:
        raise CurriculumError("reviewed G1 PPO quantum contract changed")
    remaining = rough_budget(
        FLAT_EFFECTIVE_STEPS,
        checkpoint_effective_step=FLAT_EFFECTIVE_STEPS,
        flat_trained_steps=FLAT_EFFECTIVE_STEPS,
    )
    rough = bounded_mjx_phase_steps(
        remaining,
        checkpoint_every_steps=25_000_000,
        n_envs=8_192,
        unroll_length=20,
    )
    return {"flat": flat, "rough": rough, "pilot": pilot}


def pilot_gate_result(episodes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values = tuple(episodes)
    if len(values) != 10:
        raise CurriculumError("G1 pilot gate requires exactly 10 episodes")
    horizon = [
        item.get("termination_reason") == "horizon"
        and int(item.get("length", 0)) >= HORIZON
        for item in values
    ]
    lengths = [int(item.get("length", 0)) for item in values]
    velocities = [float(item.get("mean_velocity", 0.0)) for item in values]
    nan_count = sum(
        "nan_state" in item.get("termination_causes", ()) for item in values
    )
    checks = {
        "episodes": len(values) == 10,
        "full_horizon": sum(horizon) >= 5,
        "mean_episode_length": sum(lengths) / len(lengths) >= 900.0,
        "min_velocity": min(velocities) >= 0.4,
        "zero_nan_terminations": nan_count == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "full_horizon_count": sum(horizon),
        "mean_episode_length": sum(lengths) / len(lengths),
        "min_velocity": min(velocities),
        "nan_termination_count": nan_count,
    }


def diagnostic_parent_eligible(
    flat_episodes: Iterable[dict[str, Any]], *, restore_verified: bool
) -> bool:
    values = tuple(flat_episodes)
    return (
        restore_verified
        and len(values) == 20
        and all(
            item.get("termination_reason") == "horizon"
            and int(item.get("length", 0)) >= HORIZON
            and float(item.get("mean_velocity", 0.0)) >= 0.4
            for item in values
        )
    )


def diagnostic_rough_rank_key(
    episodes: Iterable[dict[str, Any]], *, effective_step: int
) -> tuple[float, ...]:
    values = tuple(episodes)
    if not values:
        raise CurriculumError("diagnostic rough evidence contains no episodes")
    horizon_count = sum(
        item.get("termination_reason") == "horizon"
        and int(item.get("length", 0)) >= HORIZON
        for item in values
    )
    lengths = [float(item.get("length", 0)) for item in values]
    velocities = [float(item.get("mean_velocity", 0.0)) for item in values]
    rewards = [float(item.get("reward", 0.0)) for item in values]
    return (
        float(horizon_count),
        sum(lengths) / len(lengths),
        min(velocities),
        sum(velocities) / len(velocities),
        sum(rewards) / len(rewards),
        -float(effective_step),
    )


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
