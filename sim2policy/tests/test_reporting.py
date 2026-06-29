import json
from pathlib import Path

from sim2policy.evaluate import _jsonable, seed_schedule
from sim2policy.reporting import (
    aggregate_episodes,
    calculate_cost,
    comparison_table,
    threshold_crossing,
    write_markdown_report,
    write_metrics,
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


def test_success_and_no_success_reports(tmp_path: Path) -> None:
    base = {
        "run_id": "report",
        "backend": "sb3",
        "environment": "Pendulum-v1",
        "checkpoint": "final.zip",
        "seeds": [0, 1],
        "episodes": [{"seed": 0, "reward": 1.0, "length": 2}],
        "aggregate": {"mean_reward": 5.0, "std_reward": 0.5, "episodes": 1},
        "success": {"met": True, "criterion": "mean_reward >= 1"},
        "runtime_seconds": 3.0,
        "benchmark": {
            "hourly_rate": None,
            "currency": None,
            "rate_date": None,
            "estimated_cost": None,
            "gpu_utilization_percent": None,
        },
        "threshold_crossing": {"step": 10, "seconds": 2.0},
        "device": {"platform": "test"},
        "versions": {},
    }
    metrics_path = write_metrics(tmp_path / "metrics.json", base)
    payload = json.loads(metrics_path.read_text())
    assert payload["schema_version"] == 1
    summary = write_markdown_report(base, tmp_path / "summary.md").read_text()
    assert "Threshold first reached at step 10" in summary

    base["success"] = {"met": False, "criterion": "mean_reward >= 10"}
    base["threshold_crossing"] = None
    summary = write_markdown_report(base, tmp_path / "summary-fail.md").read_text()
    assert "Threshold was not reached" in summary
    assert "unavailable" in summary


def test_metrics_schema_required_fields_are_present() -> None:
    schema = json.loads((Path(__file__).parents[1] / "docs/metrics.schema.json").read_text())
    assert schema["properties"]["schema_version"]["const"] == 1
    for required in ("run_id", "backend", "environment", "episodes", "aggregate", "success"):
        assert required in schema["required"]


def test_jsonable_converts_numpy_like_values() -> None:
    class Scalar:
        def item(self) -> float:
            return 1.25

    class Array:
        def tolist(self) -> list[int]:
            return [1, 2]

    assert _jsonable({"x": Scalar(), "y": Array()}) == {"x": 1.25, "y": [1, 2]}


def test_comparison_table_context_and_partial_values() -> None:
    table = comparison_table(
        [
            {
                "backend": "sb3",
                "environment": "HalfCheetah-v5",
                "success": {"met": True, "criterion": "mean_reward >= 1"},
                "seeds": [0, 1],
                "runtime_seconds": 12.5,
                "device": {"platform": "aws-g6"},
                "benchmark": {"gpu_utilization_percent": None, "estimated_cost": 0.01},
            },
            {
                "backend": "mjx",
                "environment": "Go1",
                "success": {"met": False, "criterion": "locomotion"},
                "benchmark": {},
            },
        ]
    )
    assert "aws-g6" in table
    assert "unavailable" in table
