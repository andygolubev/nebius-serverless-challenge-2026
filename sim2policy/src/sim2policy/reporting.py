from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

METRICS_SCHEMA_VERSION = 1


def aggregate_episodes(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    rewards = [float(item["reward"]) for item in episodes]
    lengths = [int(item["length"]) for item in episodes]
    aggregate: dict[str, Any] = {
        "mean_reward": statistics.fmean(rewards),
        "std_reward": statistics.pstdev(rewards) if len(rewards) > 1 else 0.0,
        "mean_episode_length": statistics.fmean(lengths),
        "episodes": len(episodes),
    }
    # Locomotion episodes (MJX) additionally carry `mean_velocity`/`fell`; add the
    # same stability fields `checkpoint_selection.EvaluationEvidence` computes so
    # final-acceptance hard/preferred gates can be evaluated from this aggregate.
    if episodes and all("mean_velocity" in item for item in episodes):
        velocities = [float(item["mean_velocity"]) for item in episodes]
        aggregate["mean_velocity"] = statistics.fmean(velocities)
        aggregate["min_velocity"] = min(velocities)
        aggregate["no_fall_count"] = sum(not bool(item.get("fell", False)) for item in episodes)
    return aggregate


def calculate_cost(runtime_seconds: float, hourly_rate: float | None) -> float | None:
    return None if hourly_rate is None else runtime_seconds / 3600 * hourly_rate


def threshold_crossing(
    points: list[dict[str, float | int]], threshold: float
) -> dict[str, float | int] | None:
    if not points:
        return None
    started = float(points[0]["wall_time"])
    for point in points:
        if float(point["value"]) >= threshold:
            return {
                "step": int(point["step"]),
                "seconds": float(point["wall_time"]) - started,
            }
    return None


def load_reward_points(log_dir: Path) -> list[dict[str, float | int]]:
    try:
        from tensorboard.backend.event_processing.event_accumulator import (  # type: ignore[import-untyped]
            EventAccumulator,
        )
    except ImportError as exc:  # pragma: no cover - base dependency
        raise RuntimeError("TensorBoard is required to parse reward logs") from exc
    points: list[dict[str, float | int]] = []
    for event_file in sorted(log_dir.rglob("events.out.tfevents.*")):
        accumulator = EventAccumulator(str(event_file), size_guidance={"scalars": 0})
        accumulator.Reload()
        tags = accumulator.Tags().get("scalars", [])
        tag = next(
            (name for name in ("eval/mean_reward", "rollout/ep_rew_mean") if name in tags), None
        )
        if tag:
            points.extend(
                {"step": event.step, "value": event.value, "wall_time": event.wall_time}
                for event in accumulator.Scalars(tag)
            )
    unique = {(int(point["step"]), float(point["wall_time"])): point for point in points}
    return sorted(
        unique.values(), key=lambda point: (int(point["step"]), float(point["wall_time"]))
    )


def write_reward_curve(points: list[dict[str, float | int]], output: Path) -> Path:
    if not points:
        raise ValueError("no reward points available")
    import matplotlib.pyplot as plt

    output.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(figsize=(8, 4.5))
    axes.plot([point["step"] for point in points], [point["value"] for point in points])
    axes.set(title="Training reward", xlabel="Environment steps", ylabel="Mean episode reward")
    axes.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)
    return output


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
    matrix_digest = metrics.get("matrix_digest")
    if matrix_digest:
        lines.append(f"- Campaign matrix digest: `{matrix_digest}`")
    selected_checkpoint = metrics.get("selected_checkpoint")
    if isinstance(selected_checkpoint, dict):
        lines.append(
            f"- Selected checkpoint: step {selected_checkpoint.get('effective_step')} "
            f"(`{selected_checkpoint.get('sha256')}`)"
        )
    seed_roles = metrics.get("seed_roles")
    if isinstance(seed_roles, dict):
        lines.append(
            f"- Selection seeds: {seed_roles.get('selection')}; "
            f"final seeds: {seed_roles.get('final')}"
        )
    ranking_explanation = metrics.get("ranking_explanation")
    if isinstance(ranking_explanation, dict):
        lines.append(
            f"- Ranking rule: `{ranking_explanation.get('kind')}` "
            f"over {ranking_explanation.get('fields')}"
        )
    acceptance = metrics.get("acceptance")
    if isinstance(acceptance, dict):
        hard = acceptance.get("hard", {})
        preferred = acceptance.get("preferred", {})
        lines.append(
            f"- Hard floor passed: **{hard.get('passed')}**; "
            f"preferred target passed: **{preferred.get('passed')}**"
        )
    if len(lines) > 1 and lines[-1] != "":
        lines.append("")
    threshold = metrics.get("threshold_crossing")
    lines.append(
        "Threshold was not reached within the training budget."
        if threshold is None
        else (
            f"Threshold first reached at step {threshold['step']} "
            f"after {threshold['seconds']} seconds."
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return output


def comparison_table(metrics_documents: list[dict[str, Any]]) -> str:
    rows = [
        "| Backend | Environment | Success criterion | Seeds | Hardware | "
        "Runtime (s) | GPU util. | Cost |",
        "|---|---|---|---|---|---:|---:|---:|",
    ]
    for item in metrics_documents:
        benchmark = item.get("benchmark", {})
        rows.append(
            (
                "| {backend} | {environment} | {criterion}: {success} | {seeds} | "
                "{hardware} | {runtime} | {util} | {cost} |"
            ).format(
                backend=item["backend"],
                environment=item["environment"],
                criterion=item["success"].get("criterion", "unspecified"),
                success=item["success"]["met"],
                seeds=",".join(str(seed) for seed in item.get("seeds", [])) or "unavailable",
                hardware=item.get("device", {}).get("platform", "unavailable"),
                runtime=item.get("runtime_seconds", "unavailable"),
                util=benchmark.get("gpu_utilization_percent", "unavailable"),
                cost=benchmark.get("estimated_cost", "unavailable"),
            )
        )
    return "\n".join(rows) + "\n"
