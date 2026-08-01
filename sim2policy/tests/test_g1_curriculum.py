from __future__ import annotations

import pytest

from sim2policy.g1_curriculum import (
    TOTAL_STEPS,
    CurriculumError,
    bounded_mjx_phase_steps,
    flat_gate_result,
    provenance_chain,
    rough_budget,
    selected_flat_gate,
)


def _episode(*, velocity: float = 0.5, fell: bool = False, length: int = 1000) -> dict[str, object]:
    return {"mean_velocity": velocity, "fell": fell, "length": length}


def test_flat_gate_requires_full_horizon_motion_not_reward_or_standing() -> None:
    standing = flat_gate_result(100_000_000, [_episode(velocity=0.0) for _ in range(10)])
    short = flat_gate_result(150_000_000, [_episode(length=20) for _ in range(10)])
    passing = flat_gate_result(200_000_000, [_episode() for _ in range(10)])
    assert not standing.passed and not short.passed and passing.passed
    assert selected_flat_gate((standing, short, passing)) == passing
    assert rough_budget(passing.step) + passing.step == TOTAL_STEPS


def test_provenance_chain_records_measured_rough_steps_not_just_budget() -> None:
    evidence = provenance_chain(
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        flat_config_digest="c" * 64,
        rough_config_digest="d" * 64,
        flat_checkpoint_digest="e" * 64,
        rough_checkpoint_digest="f" * 64,
        selected_flat_step=100_000_000,
        rough_effective_steps=25_000_000,
        phase_outcomes={"flat": "passed", "rough": "trained"},
    )
    assert evidence["flat"]["effective_steps"] == 100_000_000
    assert evidence["rough"]["effective_steps"] == 25_000_000
    assert evidence["rough"]["budget_effective_steps"] == rough_budget(100_000_000)
    assert evidence["measured_total_steps"] == 125_000_000
    assert evidence["effective_total_steps"] == TOTAL_STEPS
    assert "provenance_digest" in evidence


def test_provenance_chain_rejects_rough_steps_over_its_remaining_budget() -> None:
    with pytest.raises(CurriculumError, match="remaining budget"):
        provenance_chain(
            matrix_digest="a" * 64,
            image_digest="sha256:" + "b" * 64,
            flat_config_digest="c" * 64,
            rough_config_digest="d" * 64,
            flat_checkpoint_digest="e" * 64,
            rough_checkpoint_digest="f" * 64,
            selected_flat_step=100_000_000,
            rough_effective_steps=rough_budget(100_000_000) + 1,
            phase_outcomes={"flat": "passed", "rough": "trained"},
        )


def test_mjx_phase_requests_are_bounded_below_the_effective_step_ceiling() -> None:
    flat = bounded_mjx_phase_steps(
        200_000_000,
        checkpoint_every_steps=25_000_000,
        n_envs=8_192,
        unroll_length=20,
    )
    assert flat == 199_229_440
    remaining = rough_budget(200_000_000, checkpoint_effective_step=flat)
    rough = bounded_mjx_phase_steps(
        remaining,
        checkpoint_every_steps=25_000_000,
        n_envs=8_192,
        unroll_length=20,
    )
    assert rough == 250_511_360
    assert flat + rough == 449_740_800 < TOTAL_STEPS


def test_rough_budget_uses_the_checkpoint_step_not_only_the_gate_label() -> None:
    assert rough_budget(
        200_000_000, checkpoint_effective_step=199_229_440
    ) == 250_770_560
    with pytest.raises(CurriculumError, match="no later"):
        rough_budget(200_000_000, checkpoint_effective_step=200_540_160)


def test_rough_budget_charges_all_flat_training_not_only_the_selected_checkpoint() -> None:
    remaining = rough_budget(
        100_000_000,
        checkpoint_effective_step=99_614_720,
        flat_trained_steps=199_229_440,
    )
    assert remaining == TOTAL_STEPS - 199_229_440

    with pytest.raises(CurriculumError, match="cannot precede"):
        rough_budget(
            100_000_000,
            checkpoint_effective_step=99_614_720,
            flat_trained_steps=90_000_000,
        )
