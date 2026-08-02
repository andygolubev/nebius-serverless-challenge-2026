"""Nebius-only diagnostic sweep and bounded pilot for G1 recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import list_step_checkpoints, load_checkpoint_metadata
from sim2policy.checkpoint_selection import evaluate_candidates, select_checkpoint
from sim2policy.config import load_config
from sim2policy.g1_curriculum import (
    PILOT_EFFECTIVE_STEPS,
    PILOT_STEP_CEILING,
    diagnostic_parent_eligible,
    diagnostic_rough_rank_key,
    pilot_gate_result,
)
from sim2policy.g1_transition import (
    TRANSITION_RELATIVE_PATH,
    build_transition_record,
    verify_transition_record,
    write_immutable_local,
)
from sim2policy.hosted_g1_curriculum import _parse_overrides
from sim2policy.run import create_run_paths
from sim2policy.storage import ArtifactStore
from sim2policy.train_mjx import (
    _prepare_resume_checkpoint,
    _verify_brax_supported_tuple,
    evaluate_mjx,
    train_mjx,
)

SOURCE_ENVIRONMENT = "G1JoystickFlatTerrain"
SWEEP_RELATIVE_PATH = "report/g1-diagnostic-sweep.json"
PILOT_RELATIVE_PATH = "report/g1-pilot-gate.json"


class RecoveryError(ValueError):
    pass


def _digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _selection_schedule(seeds: Sequence[int], episodes_per_seed: int) -> list[int]:
    if list(seeds) != [101, 151, 211, 271, 331] or episodes_per_seed <= 0:
        raise RecoveryError("G1 recovery requires the reviewed selection seeds")
    return [seed for seed in seeds for _ in range(episodes_per_seed)]


def run_diagnostic_sweep(
    *,
    source_config_path: str | Path,
    flat_config_path: str | Path,
    rough_config_path: str | Path,
    source_run_id: str,
    run_id: str,
    runs_root: Path,
    matrix_digest: str,
    image_digest: str,
    selection_seeds: Sequence[int],
    episodes_per_seed: int,
    config_overrides: dict[str, Any],
) -> dict[str, Any]:
    if episodes_per_seed != 4:
        raise RecoveryError("diagnostic sweep requires four episodes per selection seed")
    schedule = _selection_schedule(selection_seeds, episodes_per_seed)
    source_config = load_config(source_config_path, config_overrides)
    flat_config = load_config(flat_config_path, config_overrides)
    rough_config = load_config(rough_config_path, config_overrides)
    if source_config.environment != SOURCE_ENVIRONMENT:
        raise RecoveryError("diagnostic source is not the rejected G1 flat environment")

    source_paths = create_run_paths(source_run_id, runs_root)
    ArtifactStore(source_config.storage, source_run_id).download_tree(
        source_paths.root, ("checkpoints",)
    )
    checkpoints = [path for _, path in list_step_checkpoints(source_paths.checkpoints)]
    if not checkpoints:
        raise RecoveryError("rejected campaign has no retained flat checkpoints")

    sweep_paths = create_run_paths(run_id, runs_root)
    candidates: list[dict[str, Any]] = []
    for checkpoint in checkpoints:
        metadata = load_checkpoint_metadata(checkpoint)
        flat_episodes, flat_runtime = evaluate_mjx(
            checkpoint,
            flat_config,
            seeds=schedule,
            allowed_source_environment=SOURCE_ENVIRONMENT,
        )
        rough_episodes, rough_runtime = evaluate_mjx(
            checkpoint,
            rough_config,
            seeds=schedule,
            allowed_source_environment=SOURCE_ENVIRONMENT,
        )
        verification_paths = create_run_paths(
            f"{run_id}-restore-{metadata.step}", runs_root
        )
        raw = _prepare_resume_checkpoint(
            checkpoint,
            rough_config,
            verification_paths,
            allowed_source_environment=SOURCE_ENVIRONMENT,
        )
        restore = _verify_brax_supported_tuple(
            raw, verification_paths.report / "g1-restore-verification.json"
        )
        is_eligible = diagnostic_parent_eligible(
            flat_episodes, restore_verified=bool(restore)
        )
        candidates.append(
            {
                "checkpoint": {
                    "name": checkpoint.name,
                    "effective_step": metadata.step,
                    "sha256": metadata.sha256,
                    "environment": metadata.environment,
                },
                "flat": {"episodes": flat_episodes, "runtime_seconds": flat_runtime},
                "rough": {"episodes": rough_episodes, "runtime_seconds": rough_runtime},
                "restore": restore,
                "eligible": is_eligible,
                "rough_rank_key": list(
                    diagnostic_rough_rank_key(
                        rough_episodes, effective_step=metadata.step
                    )
                ),
            }
        )

    eligible_candidates = [item for item in candidates if item["eligible"]]
    selected = (
        max(eligible_candidates, key=lambda item: tuple(item["rough_rank_key"]))
        if eligible_candidates
        else None
    )
    result = {
        "schema_version": 1,
        "kind": "evaluation_only",
        "source_run_id": source_run_id,
        "source_environment": SOURCE_ENVIRONMENT,
        "matrix_digest": matrix_digest,
        "image_digest": image_digest,
        "selection_seeds": list(selection_seeds),
        "episodes_per_seed": episodes_per_seed,
        "final_seeds_touched": [],
        "measured_flat_steps": max(
            item[0] for item in list_step_checkpoints(source_paths.checkpoints)
        ),
        "candidates": candidates,
        "selected_parent": None if selected is None else selected["checkpoint"],
        "outcome": "ELIGIBLE_PARENT" if selected is not None else "NEEDS_HUMAN",
    }
    output = write_immutable_local(sweep_paths.root / SWEEP_RELATIVE_PATH, result)
    store = ArtifactStore(flat_config.storage, run_id)
    store.put_immutable_json(SWEEP_RELATIVE_PATH, result)
    if not output.is_file():
        raise RecoveryError("diagnostic sweep evidence was not persisted")
    return result


def run_pilot(
    *,
    source_config_path: str | Path,
    rough_config_path: str | Path,
    source_run_id: str,
    sweep_run_id: str,
    run_id: str,
    runs_root: Path,
    matrix_digest: str,
    image_digest: str,
    selection_seeds: Sequence[int],
    episodes_per_seed: int,
    config_overrides: dict[str, Any],
) -> dict[str, Any]:
    if episodes_per_seed != 2:
        raise RecoveryError("pilot gate requires two episodes per selection seed")
    source_config = load_config(source_config_path, config_overrides)
    rough_config = load_config(
        rough_config_path,
        {**config_overrides, "training.total_steps": PILOT_EFFECTIVE_STEPS},
    )
    if PILOT_EFFECTIVE_STEPS > PILOT_STEP_CEILING:
        raise RecoveryError("pilot executable request exceeds its ceiling")

    sweep_paths = create_run_paths(sweep_run_id, runs_root)
    sweep_store = ArtifactStore(rough_config.storage, sweep_run_id)
    sweep_store.download_tree(sweep_paths.root, ("report",))
    sweep_path = sweep_paths.root / SWEEP_RELATIVE_PATH
    if not sweep_path.is_file():
        raise RecoveryError("pilot requires immutable diagnostic sweep evidence")
    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
    if (
        sweep.get("matrix_digest") != matrix_digest
        or sweep.get("image_digest") != image_digest
        or not isinstance(sweep.get("selected_parent"), dict)
    ):
        raise RecoveryError("diagnostic sweep does not authorize a pilot parent")
    parent = sweep["selected_parent"]
    source_paths = create_run_paths(source_run_id, runs_root)
    checkpoint = ArtifactStore(source_config.storage, source_run_id).resume_named_checkpoint(
        source_paths.checkpoints,
        source_config,
        checkpoint_name=str(parent["name"]),
        expected_sha256=str(parent["sha256"]),
    )

    pilot_paths = create_run_paths(run_id, runs_root)
    trainer_load_path = str(pilot_paths.root / "resume" / checkpoint.stem)
    transition = build_transition_record(
        parent_checkpoint=checkpoint,
        parent_object_key=ArtifactStore(source_config.storage, source_run_id).key_for(
            f"checkpoints/{checkpoint.name}"
        ),
        parent_sidecar_key=ArtifactStore(source_config.storage, source_run_id).key_for(
            f"checkpoints/{checkpoint.with_suffix('.zip.json').name}"
        ),
        target_run_id=run_id,
        trainer_load_path=trainer_load_path,
        matrix_digest=matrix_digest,
        image_digest=image_digest,
        flat_config_digest=_digest(source_config_path),
        rough_config_digest=_digest(rough_config_path),
        measured_flat_steps=int(sweep["measured_flat_steps"]),
        remaining_rough_budget=PILOT_STEP_CEILING,
        requested_rough_steps=PILOT_EFFECTIVE_STEPS,
        source_environment=SOURCE_ENVIRONMENT,
    )
    write_immutable_local(pilot_paths.root / TRANSITION_RELATIVE_PATH, transition)
    pilot_store = ArtifactStore(rough_config.storage, run_id)
    pilot_store.put_immutable_json(TRANSITION_RELATIVE_PATH, transition)
    verify_transition_record(
        transition,
        parent_checkpoint=checkpoint,
        target_config=rough_config,
        matrix_digest=matrix_digest,
        image_digest=image_digest,
        flat_config_digest=_digest(source_config_path),
        rough_config_digest=_digest(rough_config_path),
        target_run_id=run_id,
        trainer_load_path=trainer_load_path,
        source_environment=SOURCE_ENVIRONMENT,
    )
    train_mjx(
        rough_config,
        run_id,
        runs_root,
        resume=checkpoint,
        allowed_source_environment=SOURCE_ENVIRONMENT,
        transition_record=transition,
    )
    checkpoints = [path for _, path in list_step_checkpoints(pilot_paths.checkpoints)]
    evidence = evaluate_candidates(
        checkpoints,
        rough_config,
        run_lineage=run_id,
        selection_seeds=selection_seeds,
        final_seeds=(0, 1, 2, 3, 4),
        episodes_per_seed=episodes_per_seed,
        phase="pilot",
    )
    selected = select_checkpoint(evidence, kind="locomotion")
    gate = pilot_gate_result(selected.episodes)
    result = {
        "schema_version": 1,
        "outcome": "PILOT_METRICS_PASSED" if gate["passed"] else "NEEDS_HUMAN",
        "full_campaign_authorized": False,
        "authorization_requires_clean_cloud_audit": bool(gate["passed"]),
        "matrix_digest": matrix_digest,
        "image_digest": image_digest,
        "transition": transition,
        "selected_checkpoint": selected.inventory.to_dict(),
        "gate": gate,
        "selection_seeds": list(selection_seeds),
        "final_seeds_touched": [],
    }
    write_immutable_local(pilot_paths.root / PILOT_RELATIVE_PATH, result)
    pilot_store.put_immutable_json(PILOT_RELATIVE_PATH, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded G1 recovery stages")
    parser.add_argument("mode", choices=("sweep", "pilot"))
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--source-config", required=True)
    parser.add_argument("--flat-config", default="configs/g1_forward_flat_mjx.yaml")
    parser.add_argument("--rough-config", required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--sweep-run-id")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--set", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    from sim2policy.execution_location import require_nebius_execution
    from sim2policy.showcase_matrix import load_matrix

    args = build_parser().parse_args(argv)
    require_nebius_execution("training")
    matrix = load_matrix(args.matrix)
    overrides = _parse_overrides(args.set)
    common = {
        "source_config_path": args.source_config,
        "rough_config_path": args.rough_config,
        "source_run_id": args.source_run_id,
        "run_id": args.run_id,
        "runs_root": args.runs_root,
        "matrix_digest": matrix.digest,
        "image_digest": args.image_digest,
        "selection_seeds": matrix.campaign["selection"]["seeds"],
        "config_overrides": overrides,
    }
    if args.mode == "sweep":
        result = run_diagnostic_sweep(
            **common,
            flat_config_path=args.flat_config,
            episodes_per_seed=4,
        )
    else:
        if not args.sweep_run_id:
            raise RecoveryError("pilot requires --sweep-run-id")
        result = run_pilot(
            **common,
            sweep_run_id=args.sweep_run_id,
            episodes_per_seed=2,
        )
    print(json.dumps({"outcome": result["outcome"]}, sort_keys=True))


if __name__ == "__main__":
    main()
