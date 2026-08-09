from __future__ import annotations

import pytest

from sim2policy.g1_curriculum import (
    FLAT_EFFECTIVE_STEPS,
    PILOT_EFFECTIVE_STEPS,
    TOTAL_STEPS,
    CurriculumError,
    assert_reviewed_step_contract,
    bounded_mjx_phase_steps,
    diagnostic_parent_eligible,
    diagnostic_rough_rank_key,
    flat_gate_result,
    pilot_gate_result,
    provenance_chain,
    rough_budget,
)


def _episode(
    *,
    velocity: float = 0.5,
    length: int = 1000,
    reason: str = "horizon",
) -> dict[str, object]:
    return {
        "mean_velocity": velocity,
        "length": length,
        "reward": 1.0,
        "fell": reason != "horizon",
        "terminated": reason != "horizon",
        "termination_reason": reason,
        "termination_causes": [reason],
    }


def test_reviewed_quantum_contract_is_exact_and_below_ceiling() -> None:
    steps = assert_reviewed_step_contract()
    assert steps == {
        "flat": 199_229_440,
        "rough": 250_511_360,
        "pilot": 46_202_880,
    }
    assert steps["flat"] + steps["rough"] < TOTAL_STEPS
    assert PILOT_EFFECTIVE_STEPS < 50_000_000


def test_flat_gate_accepts_only_the_exact_reviewed_checkpoint() -> None:
    passing = flat_gate_result(
        FLAT_EFFECTIVE_STEPS, [_episode() for _ in range(10)]
    )
    assert passing.passed
    with pytest.raises(CurriculumError, match="reviewed gate"):
        flat_gate_result(100_000_000, [_episode() for _ in range(10)])


def test_flat_gate_tolerates_one_sampled_failure_but_not_two() -> None:
    """Evidence is sampled, so the gate states a tolerance rather than perfection."""
    fall = {"reason": "foot_foot_contact", "length": 640}
    one_failure = flat_gate_result(
        FLAT_EFFECTIVE_STEPS,
        [_episode(**fall), *[_episode() for _ in range(9)]],
    )
    two_failures = flat_gate_result(
        FLAT_EFFECTIVE_STEPS,
        [*[_episode(**fall) for _ in range(2)], *[_episode() for _ in range(8)]],
    )
    assert one_failure.passed
    assert one_failure.complete_horizon_count == 9
    assert not two_failures.passed
    assert two_failures.complete_horizon_count == 8


def test_terminated_episode_is_not_also_counted_as_a_velocity_failure() -> None:
    """A fall averages backwards; that is the same defect, not a second one."""
    result = flat_gate_result(
        FLAT_EFFECTIVE_STEPS,
        [
            _episode(reason="foot_foot_contact", length=120, velocity=-1.1908),
            *[_episode() for _ in range(9)],
        ],
    )
    # The fall costs a horizon, and its backwards average never reaches the
    # velocity statistic, which reports only completed episodes.
    assert result.complete_horizon_count == 9
    assert result.min_velocity > 0.4
    assert result.passed


def test_flat_gate_still_rejects_a_gait_that_is_merely_slow() -> None:
    result = flat_gate_result(
        FLAT_EFFECTIVE_STEPS,
        [_episode(velocity=0.2), *[_episode() for _ in range(9)]],
    )
    assert result.complete_horizon_count == 10
    assert not result.passed


def test_all_measured_flat_work_is_charged_before_rough_quantization() -> None:
    remaining = rough_budget(
        FLAT_EFFECTIVE_STEPS,
        checkpoint_effective_step=FLAT_EFFECTIVE_STEPS,
        flat_trained_steps=FLAT_EFFECTIVE_STEPS,
    )
    assert remaining == TOTAL_STEPS - FLAT_EFFECTIVE_STEPS
    rough = bounded_mjx_phase_steps(
        remaining,
        checkpoint_every_steps=25_000_000,
        n_envs=8_192,
        unroll_length=20,
    )
    assert rough == 250_511_360


def test_diagnostic_parent_gate_and_zero_shot_rank() -> None:
    flat = [_episode() for _ in range(20)]
    assert diagnostic_parent_eligible(flat, restore_verified=True)
    assert not diagnostic_parent_eligible(flat, restore_verified=False)
    assert not diagnostic_parent_eligible(
        [*_episode_list(19), _episode(velocity=0.39)], restore_verified=True
    )
    stronger = diagnostic_rough_rank_key(_episode_list(20), effective_step=100)
    weaker = diagnostic_rough_rank_key(
        [_episode(reason="torso_inversion"), *_episode_list(19)], effective_step=50
    )
    assert stronger > weaker


def _episode_list(count: int) -> list[dict[str, object]]:
    return [_episode() for _ in range(count)]


def test_pilot_gate_requires_all_structured_criteria() -> None:
    passing = [
        *_episode_list(5),
        *[_episode(length=800, reason="torso_inversion") for _ in range(5)],
    ]
    result = pilot_gate_result(passing)
    assert result["passed"]
    nan = [*passing[:-1], _episode(length=800, reason="nan_state")]
    assert not pilot_gate_result(nan)["passed"]
    with pytest.raises(CurriculumError, match="exactly 10"):
        pilot_gate_result(_episode_list(9))


def test_provenance_uses_fixed_forward_identities() -> None:
    evidence = provenance_chain(
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        flat_config_digest="c" * 64,
        rough_config_digest="d" * 64,
        flat_checkpoint_digest="e" * 64,
        rough_checkpoint_digest="f" * 64,
        selected_flat_step=FLAT_EFFECTIVE_STEPS,
        rough_effective_steps=25_000_000,
        phase_outcomes={"flat": "passed", "rough": "trained"},
    )
    assert evidence["flat"]["environment"] == "G1ForwardFlatTerrain"
    assert evidence["rough"]["environment"] == "G1ForwardRoughTerrain"
