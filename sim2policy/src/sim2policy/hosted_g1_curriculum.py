"""Dedicated hosted entry point for the bounded G1 flat-to-rough curriculum.

Exactly one Nebius job, one seed. This module trains `G1JoystickFlatTerrain`
from scratch, evaluates deterministic gates at 100M/150M/200M steps, resumes
the earliest passing flat checkpoint into no-push `G1JoystickRoughTerrain`
for the remaining `450M - selected_flat_step` steps, ranks retained rough
candidates, and finalizes exactly one explicit selected checkpoint.

Invariants enforced by construction, not by a runtime check:
  - No automatic second seed or second curriculum job: this function is a
    single, non-looping pipeline over one `run_id`.
  - No steps above the fixed 450M ceiling: the rough phase always trains to
    `g1_curriculum.rough_budget(selected_flat_step)`, never `total_steps`.
  - No reward mutation or threshold relaxation: the only config override
    ever applied here is `training.total_steps` for the rough resume: reward
    weights and `acceptance_criteria` (sourced from the campaign matrix) are
    never edited.
  - No final-set reselection: `evaluate_selected_final` is called exactly
    once, on the single checkpoint `checkpoint_selection.select_checkpoint`
    already chose from selection-seed evidence.
  - Rough training is never cancelled for a weak intermediate candidate:
    once started, `train_phase` runs to completion or raises; only a
    numerical, provider, or timeout failure inside that call can stop it.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import checkpoint_by_digest, list_step_checkpoints, nearest_checkpoint
from sim2policy.checkpoint_selection import (
    EvaluationEvidence,
    acceptance_from_aggregate,
    evaluate_candidates,
    evaluate_final_checkpoint,
    explain_ranking,
    select_checkpoint,
)
from sim2policy.config import RunConfig, load_config
from sim2policy.g1_curriculum import (
    FLAT_ENVIRONMENT,
    FLAT_GATES,
    ROUGH_ENVIRONMENT,
    CurriculumError,
    flat_gate_result,
    provenance_chain,
    rough_budget,
    selected_flat_gate,
)
from sim2policy.run import create_run_paths
from sim2policy import finalize as finalize_module
from sim2policy import train_mjx


def _config_digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_g1_curriculum(
    *,
    flat_config_path: str | Path,
    rough_config_path: str | Path,
    run_id: str,
    runs_root: Path,
    matrix_digest: str,
    image_digest: str,
    gallery_example_id: str,
    selection_seeds: Sequence[int],
    final_seeds: Sequence[int],
    selection_episodes_per_seed: int,
    final_episodes_per_seed: int,
    acceptance_criteria: dict[str, Any],
    min_velocity: float = 0.4,
    train_phase: Callable[..., Path] = train_mjx.train_mjx,
    evaluate_candidates_fn: Callable[..., list[EvaluationEvidence]] = evaluate_candidates,
    evaluate_final_fn: Callable[..., EvaluationEvidence] = evaluate_final_checkpoint,
    finalize_fn: Callable[..., dict[str, str]] = finalize_module.finalize_run,
) -> dict[str, Any]:
    runs_root = Path(runs_root)
    flat_config: RunConfig = load_config(flat_config_path)
    if flat_config.environment != FLAT_ENVIRONMENT:
        raise CurriculumError("flat config does not declare the reviewed flat environment")

    # --- Phase 1: flat, from scratch. --------------------------------------
    flat_run_id = f"{run_id}-flat"
    train_phase(flat_config, flat_run_id, runs_root)
    flat_checkpoint_dir = create_run_paths(flat_run_id, runs_root).checkpoints

    gate_results = []
    gate_evidence: dict[int, EvaluationEvidence] = {}
    for gate_step in FLAT_GATES:
        checkpoint = nearest_checkpoint(flat_checkpoint_dir, gate_step)
        [evidence] = evaluate_candidates_fn(
            [checkpoint],
            flat_config,
            run_lineage=flat_run_id,
            selection_seeds=selection_seeds,
            final_seeds=final_seeds,
            episodes_per_seed=selection_episodes_per_seed,
            phase="flat",
        )
        gate_evidence[gate_step] = evidence
        result = flat_gate_result(gate_step, evidence.episodes, min_velocity=min_velocity)
        gate_results.append(result)
        if result.passed:
            # Transition as soon as a gate passes; later gates are not spent
            # on deterministic evaluation once the earliest pass is found.
            break

    selected_gate = selected_flat_gate(gate_results)
    flat_config_digest = _config_digest(flat_config_path)
    flat_phase_lineage = {
        "environment": FLAT_ENVIRONMENT,
        "config_digest": flat_config_digest,
        "gates": [
            {
                "step": item.step,
                "passed": item.passed,
                "no_fall_count": item.no_fall_count,
                "min_velocity": item.min_velocity,
                "complete_horizon_count": item.complete_horizon_count,
                "checkpoint_sha256": gate_evidence[item.step].inventory.sha256,
                "checkpoint_effective_step": gate_evidence[item.step].inventory.effective_step,
            }
            for item in gate_results
        ],
        "selected_step": selected_gate.step if selected_gate is not None else None,
        "outcome": "passed" if selected_gate is not None else "failed",
    }

    if selected_gate is None:
        # No flat gate ever passed by 200M: rough training is prohibited
        # because there is no gait to harden. Finalize diagnostics only.
        artifacts = finalize_fn(
            str(flat_config_path),
            flat_run_id,
            runs_root,
            [],
            matrix_digest=matrix_digest,
            phase_lineage={"flat": flat_phase_lineage, "rough": None},
        )
        return {
            "outcome": "NEEDS_HUMAN",
            "reason_code": "FLAT_GATE_NEVER_PASSED",
            "phase_lineage": {"flat": flat_phase_lineage, "rough": None},
            "artifacts": artifacts,
        }

    selected_flat_inventory = gate_evidence[selected_gate.step].inventory
    flat_checkpoint_path = checkpoint_by_digest(flat_checkpoint_dir, selected_flat_inventory.sha256)

    # --- Phase 2: rough, resumed from the selected flat checkpoint. --------
    remaining = rough_budget(selected_gate.step)
    rough_config: RunConfig = load_config(rough_config_path, {"training.total_steps": remaining})
    if rough_config.environment != ROUGH_ENVIRONMENT:
        raise CurriculumError("rough config does not declare the reviewed rough environment")
    rough_run_id = f"{run_id}-rough"
    train_phase(rough_config, rough_run_id, runs_root, resume=flat_checkpoint_path)
    rough_checkpoint_dir = create_run_paths(rough_run_id, runs_root).checkpoints
    rough_checkpoints = [path for _, path in list_step_checkpoints(rough_checkpoint_dir)]
    if not rough_checkpoints:
        raise CurriculumError("rough training produced no retained checkpoint")

    rough_candidates = evaluate_candidates_fn(
        rough_checkpoints,
        rough_config,
        run_lineage=rough_run_id,
        selection_seeds=selection_seeds,
        final_seeds=final_seeds,
        episodes_per_seed=selection_episodes_per_seed,
        phase="rough",
    )
    selected_rough = select_checkpoint(rough_candidates, kind="locomotion")
    if selected_rough.inventory.effective_step > remaining:
        raise CurriculumError("selected rough checkpoint exceeds its remaining-step budget")
    ranking_explanation = explain_ranking(rough_candidates, selected_rough, kind="locomotion")

    rough_checkpoint_path = checkpoint_by_digest(
        rough_checkpoint_dir, selected_rough.inventory.sha256
    )
    final_evidence = evaluate_final_fn(
        rough_checkpoint_path,
        rough_config,
        run_lineage=rough_run_id,
        selection_seeds=selection_seeds,
        final_seeds=final_seeds,
        episodes_per_seed=final_episodes_per_seed,
    )
    aggregate = final_evidence.aggregate()
    episode_count = len(final_evidence.episodes)
    hard = acceptance_from_aggregate(aggregate, episode_count, acceptance_criteria["hard"])
    preferred = acceptance_from_aggregate(aggregate, episode_count, acceptance_criteria["preferred"])

    rough_config_digest = _config_digest(rough_config_path)
    provenance = provenance_chain(
        matrix_digest=matrix_digest,
        image_digest=image_digest,
        flat_config_digest=flat_config_digest,
        rough_config_digest=rough_config_digest,
        flat_checkpoint_digest=selected_flat_inventory.sha256,
        rough_checkpoint_digest=selected_rough.inventory.sha256,
        selected_flat_step=selected_gate.step,
        rough_effective_steps=selected_rough.inventory.effective_step,
        phase_outcomes={"flat": "passed", "rough": "trained"},
    )
    phase_lineage = {
        "flat": flat_phase_lineage,
        "rough": {
            "environment": ROUGH_ENVIRONMENT,
            "config_digest": rough_config_digest,
            "input_checkpoint_digest": selected_flat_inventory.sha256,
            "selected_checkpoint_digest": selected_rough.inventory.sha256,
            "selected_checkpoint_step": selected_rough.inventory.effective_step,
            "budget_effective_steps": remaining,
        },
        "provenance": provenance,
    }

    artifacts = finalize_fn(
        str(rough_config_path),
        rough_run_id,
        runs_root,
        [("training.total_steps", remaining)],
        gallery_example_id=gallery_example_id,
        selected_checkpoint_digest=selected_rough.inventory.sha256,
        matrix_digest=matrix_digest,
        phase_lineage=phase_lineage,
        seed_roles={"selection": list(selection_seeds), "final": list(final_seeds)},
        ranking_explanation=ranking_explanation,
        acceptance_criteria=acceptance_criteria,
    )
    hard_passed = all(hard.values())
    preferred_passed = all(preferred.values())
    outcome = "ACCEPTED" if hard_passed and preferred_passed else ("REJECTED" if not hard_passed else "NEEDS_HUMAN")
    return {
        "outcome": outcome,
        "hard": hard,
        "preferred": preferred,
        "phase_lineage": phase_lineage,
        "artifacts": artifacts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the bounded G1 flat-to-rough curriculum")
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--flat-config", required=True)
    parser.add_argument("--rough-config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--image-digest", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    from sim2policy.execution_location import require_nebius_execution

    require_nebius_execution("training")
    args = build_parser().parse_args(argv)
    from sim2policy.showcase_matrix import load_matrix

    matrix = load_matrix(args.matrix)
    card = matrix.card("g1")
    campaign = matrix.campaign
    result = run_g1_curriculum(
        flat_config_path=args.flat_config,
        rough_config_path=args.rough_config,
        run_id=args.run_id,
        runs_root=args.runs_root,
        matrix_digest=matrix.digest,
        image_digest=args.image_digest,
        gallery_example_id=card["gallery_example_id"],
        selection_seeds=campaign["selection"]["seeds"],
        final_seeds=campaign["final"]["seeds"],
        selection_episodes_per_seed=campaign["selection"]["episodes_per_seed"],
        final_episodes_per_seed=campaign["final"]["episodes_per_seed"],
        acceptance_criteria=card["acceptance"],
    )
    print(json.dumps({"outcome": result["outcome"]}, sort_keys=True))
    if result["outcome"] == "NEEDS_HUMAN":
        raise SystemExit(30)
    if result["outcome"] == "REJECTED":
        raise SystemExit(20)


if __name__ == "__main__":
    main()
