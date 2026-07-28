from __future__ import annotations

# ruff: noqa: E501, I001

from sim2policy.checkpoint import CheckpointInventory
from sim2policy.checkpoint_selection import (
    EvaluationEvidence,
    SelectionError,
    acceptance_from_aggregate,
    explain_ranking,
    select_checkpoint,
    validate_seed_roles,
)


def _candidate(step: int, *, reward: float, velocity: float = 0.5, fell: bool = False) -> EvaluationEvidence:
    inventory = CheckpointInventory("mjx", "run", step, f"step-{step}.zip", f"{step:064x}", "rough", "G1JoystickRoughTerrain", True)
    episodes = tuple(
        {"seed": seed, "reward": reward, "length": 1000, "mean_velocity": velocity, "fell": fell}
        for seed in (101, 151, 211, 271, 331)
    )
    return EvaluationEvidence(inventory, "selection", (101, 151, 211, 271, 331), episodes, 1.0, "test")


def test_locomotion_stability_outranks_reward_and_earlier_tie_wins() -> None:
    stable = _candidate(25_000_000, reward=1.0)
    reward_only = _candidate(50_000_000, reward=99.0, fell=True)
    assert select_checkpoint((stable, reward_only), kind="locomotion") == stable
    later_tie = _candidate(50_000_000, reward=1.0)
    assert select_checkpoint((stable, later_tie), kind="locomotion") == stable


def test_a_later_checkpoint_that_regressed_never_wins() -> None:
    """Training longer is not evidence of being better; the ranking decides."""
    best = _candidate(100_000_000, reward=5.0, velocity=0.9)
    regressed = _candidate(125_000_000, reward=5.0, velocity=0.6)
    assert select_checkpoint((best, regressed), kind="locomotion") == best
    assert select_checkpoint((regressed, best), kind="locomotion") == best


def test_selection_refuses_an_empty_candidate_set() -> None:
    try:
        select_checkpoint((), kind="locomotion")
    except SelectionError:
        pass
    else:  # pragma: no cover - assertion form keeps the cause clear
        raise AssertionError("an empty candidate set must not yield a selection")


def test_selection_and_final_sets_can_never_overlap() -> None:
    try:
        validate_seed_roles((101, 151), (0, 1, 101))
    except SelectionError:
        pass
    else:  # pragma: no cover - assertion form keeps the cause clear
        raise AssertionError("overlapping seed sets must be rejected")


def test_explain_ranking_reports_selected_and_runner_up_values() -> None:
    stable = _candidate(25_000_000, reward=1.0)
    reward_only = _candidate(50_000_000, reward=99.0, fell=True)
    selected = select_checkpoint((stable, reward_only), kind="locomotion")
    explanation = explain_ranking((stable, reward_only), selected, kind="locomotion")
    assert explanation["kind"] == "locomotion"
    assert explanation["candidate_count"] == 2
    assert explanation["selected"]["effective_step"] == 25_000_000
    assert explanation["runner_up"]["effective_step"] == 50_000_000
    assert explanation["fields"][0] == "no_fall_count"


def test_explain_ranking_rejects_a_candidate_that_did_not_actually_win() -> None:
    stable = _candidate(25_000_000, reward=1.0)
    reward_only = _candidate(50_000_000, reward=99.0, fell=True)
    try:
        explain_ranking((stable, reward_only), reward_only, kind="locomotion")
    except SelectionError:
        pass
    else:  # pragma: no cover - assertion form keeps the cause clear
        raise AssertionError("explanation must describe the actual winner")


def test_acceptance_from_aggregate_evaluates_hard_and_preferred_criteria() -> None:
    aggregate = {
        "mean_reward": 1.0,
        "mean_episode_length": 1000.0,
        "mean_velocity": 0.55,
        "min_velocity": 0.45,
        "no_fall_count": 5,
    }
    hard = acceptance_from_aggregate(
        aggregate, 5, {"episodes": 5, "no_fall": True, "min_velocity": 0.4}
    )
    preferred = acceptance_from_aggregate(
        aggregate, 5, {"episodes": 5, "no_fall": True, "min_velocity": 0.4, "mean_velocity": 0.6}
    )
    assert all(hard.values())
    assert preferred["mean_velocity"] is False
