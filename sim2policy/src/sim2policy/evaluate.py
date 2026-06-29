from __future__ import annotations

import argparse
import importlib
import platform
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import validate_checkpoint
from sim2policy.config import RunConfig, load_config
from sim2policy.reporting import (
    aggregate_episodes,
    calculate_cost,
    write_markdown_report,
    write_metrics,
)
from sim2policy.run import package_versions
from sim2policy.storage import ArtifactStore


def seed_schedule(episodes: int, seeds: list[int]) -> list[int]:
    return [seeds[index % len(seeds)] for index in range(episodes)]


def evaluate_sb3(checkpoint: Path, config: RunConfig) -> tuple[list[dict[str, Any]], float]:
    try:
        gym = importlib.import_module("gymnasium")
        PPO = importlib.import_module("stable_baselines3").PPO
    except ImportError as exc:
        raise RuntimeError("SB3 evaluation requires the sb3 dependency group") from exc
    validate_checkpoint(checkpoint, config)
    model = PPO.load(checkpoint, device=config.training.device)
    episodes: list[dict[str, Any]] = []
    started = time.monotonic()
    for index, seed in enumerate(
        seed_schedule(config.evaluation.episodes, config.evaluation.seeds)
    ):
        env = gym.make(config.environment)
        observation, _ = env.reset(seed=seed)
        reward_sum = 0.0
        length = 0
        info: dict[str, Any] = {}
        while True:
            action, _ = model.predict(observation, deterministic=True)
            observation, reward, terminated, truncated, info = env.step(action)
            reward_sum += float(reward)
            length += 1
            if terminated or truncated:
                break
        env.close()
        episodes.append(
            {
                "index": index,
                "seed": seed,
                "reward": reward_sum,
                "length": length,
                "final_info": info,
            }
        )
    return episodes, time.monotonic() - started


def evaluate(checkpoint: Path, config: RunConfig, run_id: str, run_root: Path) -> dict[str, Any]:
    if config.backend != "sb3":
        from sim2policy.train_mjx import evaluate_mjx

        episodes, runtime = evaluate_mjx(checkpoint, config)
    else:
        episodes, runtime = evaluate_sb3(checkpoint, config)
    aggregate = aggregate_episodes(episodes)
    if config.success.kind == "mean_reward":
        met = aggregate["mean_reward"] >= float(config.success.threshold or 0)
        criterion = f"mean_reward >= {config.success.threshold}"
    else:
        met = all(bool(item.get("success")) for item in episodes)
        criterion = f"velocity >= {config.success.min_velocity} and not fallen"
    estimated_cost = calculate_cost(runtime, config.reporting.hourly_rate)
    metrics = {
        "run_id": run_id,
        "backend": config.backend,
        "environment": config.environment,
        "checkpoint": checkpoint.name,
        "seeds": config.evaluation.seeds,
        "episodes": episodes,
        "aggregate": aggregate,
        "success": {"met": met, "criterion": criterion},
        "runtime_seconds": runtime,
        "benchmark": {
            "hourly_rate": config.reporting.hourly_rate,
            "currency": config.reporting.currency,
            "rate_date": config.reporting.rate_date,
            "estimated_cost": estimated_cost,
            "gpu_utilization_percent": None,
        },
        "threshold_crossing": None,
        "device": {"platform": platform.platform(), "requested": config.training.device},
        "versions": package_versions(),
    }
    report_dir = run_root / "report"
    write_metrics(report_dir / "metrics.json", metrics)
    write_markdown_report(metrics, report_dir / "summary.md")
    ArtifactStore(config.storage, run_id).sync_tree(run_root, required=config.storage.mode == "s3")
    return metrics


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    args = parser.parse_args(argv)
    config = load_config(args.config)
    evaluate(args.checkpoint, config, args.run_id, args.runs_root / args.run_id)


if __name__ == "__main__":
    main()
