from sim2policy.evaluate import seed_schedule
from sim2policy.reporting import (
    aggregate_episodes,
    calculate_cost,
    comparison_table,
    threshold_crossing,
)


def test_seed_schedule_and_aggregates() -> None:
    assert seed_schedule(6, [1, 2]) == [1, 2, 1, 2, 1, 2]
    aggregate = aggregate_episodes([{"reward": 1, "length": 2}, {"reward": 3, "length": 4}])
    assert aggregate["mean_reward"] == 2
    assert aggregate["std_reward"] == 1


def test_cost_and_unavailable_comparison() -> None:
    assert calculate_cost(1800, 2.0) == 1.0
    assert calculate_cost(1800, None) is None
    table = comparison_table(
        [{"backend": "sb3", "environment": "Ant-v5", "success": {"met": False}}]
    )
    assert "unavailable" in table


def test_threshold_crossing() -> None:
    points = [
        {"step": 10, "value": 1.0, "wall_time": 100.0},
        {"step": 20, "value": 5.0, "wall_time": 106.0},
    ]
    assert threshold_crossing(points, 4.0) == {"step": 20, "seconds": 6.0}
    assert threshold_crossing(points, 6.0) is None
