from __future__ import annotations

from pathlib import Path

import pytest

from sim2policy.config import ConfigError, load_config
from sim2policy.locomotion_gate import (
    MIN_GATE_PASS_PROBABILITY,
    gate_pass_probability,
    minimum_reliability_for,
)
from sim2policy.locomotion_reward import (
    MIN_WALK_TO_STAND_RATIO,
    T1_ALIVE_SCALE,
    SurvivalRewardError,
    check_survival_reward,
    walk_vs_stand_ratio,
)
from sim2policy.showcase_matrix import MatrixError, load_matrix

ROOT = Path(__file__).parents[1]
MATRIX = ROOT / "configs/showcase_training_matrix.yaml"


# --- the arithmetic that made the old gate unfundable ------------------------


def test_the_old_g1_gate_was_effectively_unreachable() -> None:
    """8/10 measured -> ~0.80 reliability; 10/10 and 20/20 pass ~1 time in 1000."""
    assert gate_pass_probability(10, 10, 0.80) == pytest.approx(0.1074, abs=1e-3)
    assert gate_pass_probability(20, 20, 0.80) == pytest.approx(0.0115, abs=1e-3)
    combined = gate_pass_probability(10, 10, 0.80) * gate_pass_probability(20, 20, 0.80)
    assert combined < 0.002


def test_the_new_gate_is_clearable_by_a_good_policy() -> None:
    assert gate_pass_probability(10, 9, 0.95) > 0.9
    assert gate_pass_probability(20, 18, 0.95) > 0.9


def test_the_new_gate_still_rejects_an_unreliable_policy() -> None:
    assert gate_pass_probability(10, 9, 0.80) < 0.4
    assert gate_pass_probability(20, 18, 0.80) < 0.25


def test_pass_probability_is_monotonic_and_bounded() -> None:
    assert gate_pass_probability(20, 18, 1.0) == pytest.approx(1.0)
    assert gate_pass_probability(20, 18, 0.0) == pytest.approx(0.0)
    assert gate_pass_probability(20, 0, 0.5) == pytest.approx(1.0)
    previous = 0.0
    for tenth in range(11):
        value = gate_pass_probability(20, 18, tenth / 10)
        assert value >= previous
        previous = value


def test_minimum_reliability_matches_the_pass_probability_floor() -> None:
    for episodes, required in ((10, 10), (20, 20), (10, 9), (20, 18)):
        threshold = minimum_reliability_for(episodes, required)
        assert gate_pass_probability(
            episodes, required, threshold
        ) == pytest.approx(MIN_GATE_PASS_PROBABILITY, abs=1e-3)


@pytest.mark.parametrize(
    "episodes, required, reliability",
    [(0, 0, 0.5), (10, 11, 0.5), (10, -1, 0.5), (10, 5, 1.5), (10, 5, -0.1)],
)
def test_pass_probability_rejects_nonsense(
    episodes: int, required: int, reliability: float
) -> None:
    with pytest.raises(ValueError):
        gate_pass_probability(episodes, required, reliability)


# --- the matrix refuses to fund an unclearable gate --------------------------


def test_shipped_matrix_gates_all_clear_the_floor() -> None:
    matrix = load_matrix(MATRIX)
    for name in ("go1", "g1"):
        acceptance = matrix.card(name)["acceptance"]
        for level in ("hard", "preferred"):
            criteria = acceptance[level]
            chance = gate_pass_probability(
                int(criteria["episodes"]),
                int(criteria["required_horizons"]),
                float(criteria["assumed_reliability"]),
            )
            assert chance >= MIN_GATE_PASS_PROBABILITY


def test_go1_keeps_the_exact_count_it_actually_achieved() -> None:
    """Go1 measured 20/20; relaxing a gate it already clears would weaken it."""
    hard = load_matrix(MATRIX).card("go1")["acceptance"]["hard"]
    assert hard["required_horizons"] == hard["episodes"] == 20


def test_g1_gate_carries_the_reviewed_tolerance() -> None:
    hard = load_matrix(MATRIX).card("g1")["acceptance"]["hard"]
    assert (hard["required_horizons"], hard["episodes"]) == (18, 20)
    assert hard["min_velocity"] == 0.4


def _matrix_with(replacement: str, original: str) -> str:
    text = MATRIX.read_text(encoding="utf-8")
    assert original in text
    return text.replace(original, replacement)


def test_matrix_rejects_a_gate_below_the_pass_probability_floor(
    tmp_path: Path,
) -> None:
    """A gate a good-enough policy would usually fail cannot be authorized."""
    original = (
        "{episodes: 20, required_horizons: 18, assumed_reliability: 0.95, min_velocity: 0.4}"
    )
    broken = (
        "{episodes: 20, required_horizons: 20, assumed_reliability: 0.80, min_velocity: 0.4}"
    )
    path = tmp_path / "matrix.yaml"
    path.write_text(_matrix_with(broken, original), encoding="utf-8")
    with pytest.raises(MatrixError, match="passes only"):
        load_matrix(path)


def test_matrix_rejects_the_legacy_all_or_nothing_spelling(tmp_path: Path) -> None:
    original = (
        "{episodes: 20, required_horizons: 18, assumed_reliability: 0.95, min_velocity: 0.4}"
    )
    legacy = "{episodes: 20, no_fall: true, min_velocity: 0.4}"
    path = tmp_path / "matrix.yaml"
    path.write_text(_matrix_with(legacy, original), encoding="utf-8")
    with pytest.raises(MatrixError, match="no_fall is implicit"):
        load_matrix(path)


def test_matrix_requires_a_declared_reliability(tmp_path: Path) -> None:
    original = (
        "{episodes: 20, required_horizons: 18, assumed_reliability: 0.95, min_velocity: 0.4}"
    )
    undeclared = "{episodes: 20, required_horizons: 18, min_velocity: 0.4}"
    path = tmp_path / "matrix.yaml"
    path.write_text(_matrix_with(undeclared, original), encoding="utf-8")
    with pytest.raises(MatrixError, match="assumed_reliability"):
        load_matrix(path)


# --- the survival reward, and the trap it can fall into ----------------------


def test_walking_out_pays_standing_at_the_reviewed_alive_scale() -> None:
    for target in (0.8, 1.0):
        ratio = walk_vs_stand_ratio(T1_ALIVE_SCALE, target)
        assert ratio >= MIN_WALK_TO_STAND_RATIO
    # Turning the reward off entirely leaves the largest margin, and is what the
    # pinned upstream config does -- which is why nothing rewarded survival.
    assert walk_vs_stand_ratio(0.0, 0.8) > walk_vs_stand_ratio(0.25, 0.8)


def test_reviewed_alive_scale_is_accepted() -> None:
    check_survival_reward(T1_ALIVE_SCALE, target_velocity=0.8)
    check_survival_reward(T1_ALIVE_SCALE, target_velocity=1.0)


def test_a_survival_reward_that_would_pay_for_loitering_is_rejected() -> None:
    """The failure this repo already measured once, in custom-robot v9."""
    with pytest.raises(SurvivalRewardError, match="margin"):
        check_survival_reward(1.0, target_velocity=0.8)


@pytest.mark.parametrize("alive", [-0.1, float("nan")])
def test_survival_reward_rejects_invalid_numbers(alive: float) -> None:
    with pytest.raises(SurvivalRewardError, match="non-negative"):
        check_survival_reward(alive, target_velocity=0.8)


def test_survival_reward_rejects_a_boolean() -> None:
    with pytest.raises(SurvivalRewardError, match="must be a number"):
        check_survival_reward(True, target_velocity=0.8)


# --- config plumbing ---------------------------------------------------------


def test_g1_configs_declare_the_survival_reward_and_longer_horizon() -> None:
    for name in ("g1_forward_flat_mjx.yaml", "g1_forward_rough_mjx.yaml"):
        config = load_config(ROOT / "configs" / name)
        hyper = config.training.hyperparameters
        assert hyper["playground_config_overrides"]["reward_config.scales.alive"] == 0.25
        assert hyper["discounting"] == 0.99


def test_config_rejects_a_survival_reward_that_outcompetes_the_task() -> None:
    with pytest.raises(ConfigError, match="margin"):
        load_config(
            ROOT / "configs/g1_forward_rough_mjx.yaml",
            {
                "training.hyperparameters": {
                    "impl": "jax",
                    "playground_config_overrides": {
                        "push_config.enable": False,
                        "reward_config.scales.alive": 1.0,
                    },
                }
            },
        )


@pytest.mark.parametrize(
    "scale",
    [
        # The scale that defines the task. Editing it would let a run inflate
        # the very velocity the acceptance gate measures, so it must stay shut
        # even though `alive` and `termination` are now open.
        "reward_config.scales.tracking_lin_vel",
        "reward_config.scales.orientation",
        "reward_config.scales.feet_air_time",
    ],
)
def test_reward_editing_beyond_the_reviewed_scales_stays_closed(scale: str) -> None:
    with pytest.raises(ConfigError, match="unsupported MJX Playground"):
        load_config(
            ROOT / "configs/g1_forward_rough_mjx.yaml",
            {
                "training.hyperparameters": {
                    "impl": "jax",
                    "playground_config_overrides": {
                        "push_config.enable": False,
                        scale: 1.0,
                    },
                }
            },
        )
