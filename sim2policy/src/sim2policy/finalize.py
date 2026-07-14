from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import metadata_path, progression_checkpoints
from sim2policy.config import load_config, parse_override
from sim2policy.evaluate import evaluate
from sim2policy.policy_bundle import build_gallery_policy_bundle
from sim2policy.render import montage_command, render_with_fallback
from sim2policy.reporting import (
    calculate_cost,
    comparison_table,
    load_reward_points,
    write_markdown_report,
    write_metrics,
    write_reward_curve,
)
from sim2policy.run import create_run_paths
from sim2policy.runstate import (
    STATUS_COMPLETED,
    STATUS_EVALUATING,
    STATUS_RENDERING,
    RunStateStore,
)
from sim2policy.storage import ArtifactStore


def _override(value: str) -> tuple[str, Any]:
    return parse_override(value)


def _override_args(overrides: list[tuple[str, Any]]) -> list[str]:
    return [
        part
        for key, value in overrides
        for part in ("--set", f"{key}={json.dumps(value, separators=(',', ':'))}")
    ]


def _write_final_alias(checkpoint: Path) -> Path:
    alias = checkpoint.parent / "final.zip"
    shutil.copy2(checkpoint, alias)
    raw = json.loads(metadata_path(checkpoint).read_text(encoding="utf-8"))
    raw["checkpoint"] = alias.name
    metadata_path(alias).write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return alias


def finalize_run(
    config_path: str,
    run_id: str,
    runs_root: Path,
    overrides: list[tuple[str, Any]],
    compare_run_id: str | None = None,
    gallery_example_id: str | None = None,
) -> dict[str, str]:
    config = load_config(config_path, dict(overrides))
    paths = create_run_paths(run_id, runs_root)
    store = ArtifactStore(config.storage, run_id)
    state = RunStateStore(config.storage, run_id, runs_root)
    store.download_tree(paths.root, ("checkpoints", "tensorboard", "metadata", "report"))
    initial, quarter, final = progression_checkpoints(
        paths.checkpoints, config.training.total_steps
    )
    state.update_status(STATUS_RENDERING)
    child_overrides = _override_args(overrides)
    videos: list[Path] = []
    for name, checkpoint in zip(
        ("untrained", "mid", "final"), (initial, quarter, final), strict=True
    ):
        video = paths.videos / f"{name}.mp4"
        render_with_fallback(
            [
                "--config",
                config_path,
                "--checkpoint",
                str(checkpoint),
                "--output",
                str(video),
                *child_overrides,
            ]
        )
        videos.append(video)
    montage = paths.videos / "progression_montage.mp4"
    subprocess.run(montage_command(videos, montage), check=True)
    state.update_status(STATUS_EVALUATING)
    metrics = evaluate(final, config, run_id, paths.root)
    runtime_path = paths.report / "runtime.json"
    if runtime_path.is_file():
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        training_seconds = runtime.get("runtime_seconds")
        if training_seconds is not None:
            metrics["evaluation_runtime_seconds"] = metrics["runtime_seconds"]
            metrics["runtime_seconds"] = training_seconds
            metrics["benchmark"]["estimated_cost"] = calculate_cost(
                float(training_seconds), config.reporting.hourly_rate
            )
            write_metrics(paths.report / "metrics.json", metrics)
            write_markdown_report(metrics, paths.report / "summary.md")
    summary = paths.report / "summary.md"
    if summary.is_file():
        shutil.copy2(summary, paths.report / "report.md")
    points = load_reward_points(paths.tensorboard)
    if points:
        write_reward_curve(points, paths.report / "reward-curve.png")
    if compare_run_id is not None:
        comparison_root = runs_root / compare_run_id
        ArtifactStore(config.storage, compare_run_id).download_tree(comparison_root, ("report",))
        comparison_metrics = comparison_root / "report/metrics.json"
        if not comparison_metrics.is_file():
            raise RuntimeError(f"comparison metrics unavailable for run {compare_run_id}")
        other = json.loads(comparison_metrics.read_text(encoding="utf-8"))
        (paths.report / "backend-comparison.md").write_text(
            comparison_table([metrics, other]), encoding="utf-8"
        )
    final_alias = _write_final_alias(final)
    if gallery_example_id is not None:
        if not gallery_example_id or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
            for character in gallery_example_id
        ):
            raise ValueError("gallery example identity is invalid")
        runtime_image = os.environ.get("SIM2POLICY_RUNTIME_IMAGE", "local-unpublished-runtime")
        resolved = asdict(config)
        resolved["gallery_example_id"] = gallery_example_id
        resolved["runtime_image"] = runtime_image
        resolved_path = paths.report / "resolved-config.json"
        resolved_path.write_text(
            json.dumps(resolved, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raw_versions = metrics.get("versions")
        versions: dict[str, Any] = (
            {str(key): value for key, value in raw_versions.items()}
            if isinstance(raw_versions, dict)
            else {}
        )
        versions_path = paths.report / "runtime-versions.json"
        versions_path.write_text(
            json.dumps(versions, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        build_gallery_policy_bundle(
            paths.root / "bundle/policy-bundle.zip",
            run_id=run_id,
            example_id=gallery_example_id,
            backend=config.backend,
            environment=config.environment,
            checkpoint=final_alias,
            resolved_config=resolved,
            evaluation=metrics,
            versions=versions,
            runtime_image=runtime_image,
        )
    store.sync_tree(paths.root, required=store.enabled)
    artifacts = state.discover_artifacts()
    state.write_manifest(artifacts)
    state.update_status(
        STATUS_COMPLETED,
        progress={"final_checkpoint": final.name, "published_artifacts": len(artifacts)},
    )
    return artifacts


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Finalize a durable Sim2Policy cloud run")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--compare-run-id")
    parser.add_argument("--gallery-example-id")
    parser.add_argument("--set", action="append", default=[], type=_override, dest="overrides")
    args = parser.parse_args(argv)
    artifacts = finalize_run(
        args.config,
        args.run_id,
        args.runs_root,
        args.overrides,
        compare_run_id=args.compare_run_id,
        gallery_example_id=args.gallery_example_id,
    )
    print(json.dumps({"status": "complete", "artifacts": artifacts}, sort_keys=True))


if __name__ == "__main__":
    main()
