from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

METRICS_SCHEMA_VERSION = 1


def aggregate_episodes(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    rewards = [float(item["reward"]) for item in episodes]
    lengths = [int(item["length"]) for item in episodes]
    return {
        "mean_reward": statistics.fmean(rewards),
        "std_reward": statistics.pstdev(rewards) if len(rewards) > 1 else 0.0,
        "mean_length": statistics.fmean(lengths),
        "episodes": len(episodes),
    }


def calculate_cost(runtime_seconds: float, hourly_rate: float | None) -> float | None:
    return None if hourly_rate is None else runtime_seconds / 3600 * hourly_rate


def write_metrics(output: Path, metrics: dict[str, Any]) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": METRICS_SCHEMA_VERSION, **metrics}
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output


def write_markdown_report(metrics: dict[str, Any], output: Path) -> Path:
    aggregate = metrics["aggregate"]
    success = metrics["success"]
    benchmark = metrics.get("benchmark", {})
    def available(value: Any, suffix: str = "") -> str:
        return "unavailable" if value is None else f"{value}{suffix}"
    lines = [
        f"# Sim2Policy report: {metrics['run_id']}",
        "",
        f"- Backend: `{metrics['backend']}`",
        f"- Environment: `{metrics['environment']}`",
        f"- Checkpoint: `{metrics['checkpoint']}`",
        f"- Mean reward: {aggregate['mean_reward']:.3f} ± {aggregate['std_reward']:.3f}",
        f"- Success: **{success['met']}** ({success['criterion']})",
        f"- Runtime: {available(metrics.get('runtime_seconds'), ' s')}",
        f"- GPU utilization: {available(benchmark.get('gpu_utilization_percent'), '%')}",
        f"- Estimated cost: {available(benchmark.get('estimated_cost'))}",
        "",
    ]
    threshold = metrics.get("threshold_crossing")
    lines.append(
        "Threshold was not reached within the training budget."
        if threshold is None
        else f"Threshold first reached at step {threshold['step']} after {threshold['seconds']} seconds."
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return output


def comparison_table(metrics_documents: list[dict[str, Any]]) -> str:
    rows = ["| Backend | Environment | Success | Runtime (s) | GPU util. | Cost |", "|---|---|---:|---:|---:|---:|"]
    for item in metrics_documents:
        benchmark = item.get("benchmark", {})
        rows.append(
            "| {backend} | {environment} | {success} | {runtime} | {util} | {cost} |".format(
                backend=item["backend"], environment=item["environment"],
                success=item["success"]["met"], runtime=item.get("runtime_seconds", "unavailable"),
                util=benchmark.get("gpu_utilization_percent", "unavailable"),
                cost=benchmark.get("estimated_cost", "unavailable"),
            )
        )
    return "\n".join(rows) + "\n"

