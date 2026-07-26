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

from sim2policy.checkpoint import (
    checkpoint_by_digest,
    checkpoint_inventory,
    metadata_path,
    progression_checkpoints,
)
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
    selected_checkpoint_digest: str | None = None,
    matrix_digest: str | None = None,
    phase_lineage: dict[str, Any] | None = None,
    seed_roles: dict[str, Any] | None = None,
    ranking_explanation: dict[str, Any] | None = None,
    acceptance_criteria: dict[str, Any] | None = None,
) -> dict[str, str]:
    config = load_config(config_path, dict(overrides))
    paths = create_run_paths(run_id, runs_root)
    store = ArtifactStore(config.storage, run_id)
    state = RunStateStore(config.storage, run_id, runs_root)
    store.download_tree(paths.root, ("checkpoints", "tensorboard", "metadata", "report"))
    initial, quarter, final_step = progression_checkpoints(
        paths.checkpoints, config.training.total_steps
    )
    selected = (
        checkpoint_by_digest(paths.checkpoints, selected_checkpoint_digest)
        if selected_checkpoint_digest is not None
        else final_step
    )
    state.update_status(STATUS_RENDERING)
    child_overrides = _override_args(overrides)
    videos: list[Path] = []
    progression: list[dict[str, Any]] = []
    for name, checkpoint in zip(
        ("untrained", "mid", "selected", "final-step"),
        (initial, quarter, selected, final_step),
        strict=True,
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
        inventory = checkpoint_inventory(
            checkpoint,
            config,
            run_lineage=run_id,
            phase="selected" if checkpoint == selected else "training",
        )
        progression.append(
            {
                "stage": name,
                "video": video.name,
                "checkpoint": inventory.to_dict(),
                "selected": checkpoint == selected,
                "regression": checkpoint == final_step and selected != final_step,
            }
        )
    # `video_final` is the selected policy's public rollout.  Preserve the final
    # step separately so a late regression can never be hidden by replacement.
    shutil.copy2(paths.videos / "selected.mp4", paths.videos / "final.mp4")
    montage = paths.videos / "progression_montage.mp4"
    subprocess.run(
        montage_command(
            videos,
            montage,
            [f"{item['stage']}@{item['checkpoint']['effective_step']}" for item in progression],
        ),
        check=True,
    )
    state.update_status(STATUS_EVALUATING)
    metrics = evaluate(selected, config, run_id, paths.root)
    metrics["selected_checkpoint"] = checkpoint_inventory(
        selected, config, run_lineage=run_id, phase="selected"
    ).to_dict()
    metrics["final_step_checkpoint"] = checkpoint_inventory(
        final_step, config, run_lineage=run_id, phase="training"
    ).to_dict()
    metrics["progression"] = progression
    metrics["resolved_config"] = {
        "training": {"total_steps": config.training.total_steps},
        "runtime_image": os.environ.get("SIM2POLICY_RUNTIME_IMAGE"),
    }
    if matrix_digest is not None:
        metrics["matrix_digest"] = matrix_digest
    if phase_lineage is not None:
        metrics["phase_lineage"] = phase_lineage
    if seed_roles is not None:
        from sim2policy.checkpoint_selection import validate_seed_roles

        validate_seed_roles(seed_roles.get("selection", ()), seed_roles.get("final", ()))
        metrics["seed_roles"] = seed_roles
    if ranking_explanation is not None:
        metrics["ranking_explanation"] = ranking_explanation
    if acceptance_criteria is not None:
        from sim2policy.checkpoint_selection import acceptance_from_aggregate

        episode_count = len(metrics["episodes"])
        hard = acceptance_from_aggregate(
            metrics["aggregate"], episode_count, acceptance_criteria["hard"]
        )
        preferred = acceptance_from_aggregate(
            metrics["aggregate"], episode_count, acceptance_criteria["preferred"]
        )
        metrics["acceptance"] = {
            "hard": {"criteria": hard, "passed": all(hard.values())},
            "preferred": {"criteria": preferred, "passed": all(preferred.values())},
        }
    write_metrics(paths.report / "metrics.json", metrics)
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
    final_alias = _write_final_alias(selected)
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
        resolved["matrix_digest"] = matrix_digest
        resolved["selected_checkpoint"] = metrics["selected_checkpoint"]
        if phase_lineage is not None:
            resolved["phase_lineage"] = phase_lineage
        if "seed_roles" in metrics:
            resolved["seed_roles"] = metrics["seed_roles"]
        if "ranking_explanation" in metrics:
            resolved["ranking_explanation"] = metrics["ranking_explanation"]
        if "acceptance" in metrics:
            resolved["acceptance"] = metrics["acceptance"]
        resolved["measured_runtime_seconds"] = metrics.get("runtime_seconds")
        resolved["measured_cost"] = metrics.get("benchmark", {}).get("estimated_cost")
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
    curation_evidence = {
        key: metrics[key]
        for key in (
            "matrix_digest",
            "phase_lineage",
            "selected_checkpoint",
            "seed_roles",
            "ranking_explanation",
            "acceptance",
            "runtime_seconds",
        )
        if key in metrics
    }
    if "benchmark" in metrics and isinstance(metrics["benchmark"], dict):
        curation_evidence["estimated_cost"] = metrics["benchmark"].get("estimated_cost")
    state.write_manifest(artifacts, evidence=curation_evidence)
    state.update_status(
        STATUS_COMPLETED,
        progress={
            "selected_checkpoint": selected.name,
            "final_step_checkpoint": final_step.name,
            "published_artifacts": len(artifacts),
        },
    )
    return artifacts


def main(argv: Sequence[str] | None = None) -> None:
    from sim2policy.execution_location import require_nebius_execution

    require_nebius_execution("finalization")
    parser = argparse.ArgumentParser(description="Finalize a durable Sim2Policy cloud run")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--compare-run-id")
    parser.add_argument("--gallery-example-id")
    parser.add_argument("--selected-checkpoint-digest")
    parser.add_argument("--matrix-digest")
    parser.add_argument("--phase-lineage-json")
    parser.add_argument("--seed-roles-json")
    parser.add_argument("--ranking-explanation-json")
    parser.add_argument("--acceptance-criteria-json")
    parser.add_argument("--set", action="append", default=[], type=_override, dest="overrides")
    args = parser.parse_args(argv)
    artifacts = finalize_run(
        args.config,
        args.run_id,
        args.runs_root,
        args.overrides,
        compare_run_id=args.compare_run_id,
        gallery_example_id=args.gallery_example_id,
        selected_checkpoint_digest=args.selected_checkpoint_digest,
        matrix_digest=args.matrix_digest,
        phase_lineage=(json.loads(args.phase_lineage_json) if args.phase_lineage_json else None),
        seed_roles=(json.loads(args.seed_roles_json) if args.seed_roles_json else None),
        ranking_explanation=(
            json.loads(args.ranking_explanation_json) if args.ranking_explanation_json else None
        ),
        acceptance_criteria=(
            json.loads(args.acceptance_criteria_json) if args.acceptance_criteria_json else None
        ),
    )
    print(json.dumps({"status": "complete", "artifacts": artifacts}, sort_keys=True))


if __name__ == "__main__":
    main()
