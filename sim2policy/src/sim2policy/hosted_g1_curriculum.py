"""Dedicated hosted entry point for the bounded G1 flat-to-rough curriculum.

Exactly one Nebius job, one seed. This module trains `G1ForwardFlatTerrain`
from scratch in one uninterrupted request, evaluates only the exact derived
149,422,080-step boundary, publishes an immutable transition, resumes it into
`G1ForwardRoughTerrain` for the bounded remainder, ranks retained rough
candidates, and finalizes exactly one explicit selected checkpoint.

Invariants enforced by construction, not by a runtime check:
  - No automatic second seed or second curriculum job: this function is a
    single, non-looping pipeline over one `run_id`.
  - No steps above the fixed 450M ceiling: both phase requests are aligned to
    whole MJX epochs and the rough budget subtracts the measured flat checkpoint.
  - No reward mutation or threshold relaxation: the only config override
    ever applied here is bounded `training.total_steps` for the two phases: reward
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

from sim2policy import finalize as finalize_module
from sim2policy import train_mjx
from sim2policy.checkpoint import (
    checkpoint_by_digest,
    list_step_checkpoints,
    load_checkpoint_metadata,
)
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
    FLAT_EFFECTIVE_STEPS,
    FLAT_ENVIRONMENT,
    FLAT_NOMINAL_STEPS,
    ROUGH_ENVIRONMENT,
    CurriculumError,
    bounded_mjx_phase_steps,
    flat_gate_result,
    provenance_chain,
    rough_budget,
)
from sim2policy.g1_transition import (
    TRANSITION_RELATIVE_PATH,
    build_transition_record,
    verify_transition_record,
    write_immutable_local,
)
from sim2policy.run import create_run_paths
from sim2policy.storage import ArtifactStore

G1_ALLOWED_OVERRIDES = frozenset(
    {
        "storage.mode",
        "storage.bucket",
        "storage.prefix",
        "storage.endpoint_url",
        "storage.region",
        "storage.retries",
    }
)


def _config_digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _finalize_overrides(overrides: dict[str, Any], total_steps: int) -> list[tuple[str, Any]]:
    """Carry the durable destination into finalization and pin its phase budget."""
    return [
        *((key, value) for key, value in overrides.items() if key != "training.total_steps"),
        ("training.total_steps", total_steps),
    ]


def _validate_overrides(overrides: dict[str, Any]) -> None:
    unknown = sorted(set(overrides) - G1_ALLOWED_OVERRIDES)
    if unknown:
        raise CurriculumError(
            "G1 recovery forbids training, reward, seed, and gate overrides: "
            + ", ".join(unknown)
        )


def recover_g1_finalization(
    *,
    flat_config_path: str | Path,
    rough_config_path: str | Path,
    run_id: str,
    runs_root: Path,
    matrix_digest: str,
    image_digest: str,
    gallery_example_id: str,
    config_overrides: dict[str, Any],
    finalize_fn: Callable[..., dict[str, str]] = finalize_module.finalize_run,
) -> dict[str, Any]:
    """Finalize only the exact rough phase named by immutable durable evidence."""
    runs_root = Path(runs_root)
    _validate_overrides(config_overrides)
    rough_run_id = f"{run_id}-rough"
    flat_run_id = f"{run_id}-flat"
    flat_config = load_config(
        flat_config_path,
        {**config_overrides, "training.total_steps": FLAT_EFFECTIVE_STEPS},
    )
    remaining = rough_budget(
        FLAT_EFFECTIVE_STEPS,
        checkpoint_effective_step=FLAT_EFFECTIVE_STEPS,
        flat_trained_steps=FLAT_EFFECTIVE_STEPS,
    )
    raw_rough = load_config(rough_config_path, config_overrides)
    rough_steps = bounded_mjx_phase_steps(
        remaining,
        checkpoint_every_steps=raw_rough.checkpoint.every_steps,
        n_envs=raw_rough.training.n_envs,
        unroll_length=int(raw_rough.training.hyperparameters["unroll_length"]),
    )
    rough_config = load_config(
        rough_config_path,
        {**config_overrides, "training.total_steps": rough_steps},
    )
    rough_paths = create_run_paths(rough_run_id, runs_root)
    rough_store = ArtifactStore(rough_config.storage, rough_run_id)
    rough_store.download_tree(rough_paths.root, ("checkpoints", "report", "tensorboard"))
    transition_path = rough_paths.root / TRANSITION_RELATIVE_PATH
    finalization_path = rough_paths.report / "g1-finalization-input.json"
    if not transition_path.is_file() or not finalization_path.is_file():
        raise CurriculumError("immutable G1 transition or finalization input is absent")
    transition = json.loads(transition_path.read_text(encoding="utf-8"))
    finalization_input = json.loads(finalization_path.read_text(encoding="utf-8"))

    parent = transition.get("parent", {})
    flat_paths = create_run_paths(flat_run_id, runs_root)
    parent_checkpoint = ArtifactStore(flat_config.storage, flat_run_id).resume_named_checkpoint(
        flat_paths.checkpoints,
        flat_config,
        checkpoint_name=str(parent.get("checkpoint_name", "")),
        expected_sha256=str(parent.get("sha256", "")),
    )
    trainer_load_path = str(transition.get("restore", {}).get("trainer_load_path", ""))
    verify_transition_record(
        transition,
        parent_checkpoint=parent_checkpoint,
        target_config=rough_config,
        matrix_digest=matrix_digest,
        image_digest=image_digest,
        flat_config_digest=_config_digest(flat_config_path),
        rough_config_digest=_config_digest(rough_config_path),
        target_run_id=rough_run_id,
        trainer_load_path=trainer_load_path,
    )
    if (
        finalization_input.get("schema_version") != 1
        or finalization_input.get("transition") != transition
        or finalization_input.get("rough_run_id") != rough_run_id
    ):
        raise CurriculumError("G1 finalization input disagrees with the immutable transition")
    selected_digest = str(finalization_input.get("selected_checkpoint_digest", ""))
    checkpoint_by_digest(rough_paths.checkpoints, selected_digest)
    artifacts = finalize_fn(
        str(rough_config_path),
        rough_run_id,
        runs_root,
        _finalize_overrides(config_overrides, rough_steps),
        gallery_example_id=gallery_example_id,
        selected_checkpoint_digest=selected_digest,
        matrix_digest=matrix_digest,
        phase_lineage=finalization_input["phase_lineage"],
        seed_roles=finalization_input["seed_roles"],
        ranking_explanation=finalization_input["ranking_explanation"],
        acceptance_criteria=finalization_input["acceptance_criteria"],
    )
    return {"outcome": "FINALIZED_EXACT_RECOVERY", "artifacts": artifacts}


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
    config_overrides: dict[str, Any] | None = None,
    min_velocity: float = 0.4,
    train_phase: Callable[..., Path] = train_mjx.train_mjx,
    evaluate_candidates_fn: Callable[..., list[EvaluationEvidence]] = evaluate_candidates,
    evaluate_final_fn: Callable[..., EvaluationEvidence] = evaluate_final_checkpoint,
    finalize_fn: Callable[..., dict[str, str]] = finalize_module.finalize_run,
) -> dict[str, Any]:
    runs_root = Path(runs_root)
    # The campaign supplies the durable artifact destination the same way it does
    # for the single-phase paths; both curriculum phases must write to it.
    overrides = dict(config_overrides or {})
    _validate_overrides(overrides)
    raw_flat_config: RunConfig = load_config(flat_config_path, overrides)
    flat_steps = bounded_mjx_phase_steps(
        FLAT_NOMINAL_STEPS,
        checkpoint_every_steps=raw_flat_config.checkpoint.every_steps,
        n_envs=raw_flat_config.training.n_envs,
        unroll_length=int(raw_flat_config.training.hyperparameters["unroll_length"]),
    )
    if flat_steps != FLAT_EFFECTIVE_STEPS:
        raise CurriculumError("derived flat request differs from reviewed 149,422,080 steps")
    flat_config: RunConfig = load_config(
        flat_config_path, {**overrides, "training.total_steps": flat_steps}
    )
    if flat_config.environment != FLAT_ENVIRONMENT:
        raise CurriculumError("flat config does not declare the reviewed flat environment")

    # --- Phase 1: flat, from scratch. --------------------------------------
    flat_run_id = f"{run_id}-flat"
    flat_final_checkpoint = train_phase(flat_config, flat_run_id, runs_root)
    flat_trained_steps = load_checkpoint_metadata(flat_final_checkpoint).step
    if flat_trained_steps > flat_steps:
        raise CurriculumError("flat training exceeded its bounded phase request")
    if flat_trained_steps != FLAT_EFFECTIVE_STEPS:
        raise CurriculumError("flat trainer did not stop at the exact derived boundary")
    flat_checkpoint_dir = create_run_paths(flat_run_id, runs_root).checkpoints
    [flat_evidence] = evaluate_candidates_fn(
        [flat_final_checkpoint],
        flat_config,
        run_lineage=flat_run_id,
        selection_seeds=selection_seeds,
        final_seeds=final_seeds,
        episodes_per_seed=selection_episodes_per_seed,
        phase="flat-final-gate",
    )
    flat_gate = flat_gate_result(
        FLAT_EFFECTIVE_STEPS, flat_evidence.episodes, min_velocity=min_velocity
    )
    flat_config_digest = _config_digest(flat_config_path)
    flat_phase_lineage = {
        "environment": FLAT_ENVIRONMENT,
        "config_digest": flat_config_digest,
        "nominal_steps": FLAT_NOMINAL_STEPS,
        "gate": {
            "step": flat_gate.step,
            "passed": flat_gate.passed,
            "no_fall_count": flat_gate.no_fall_count,
            "min_velocity": flat_gate.min_velocity,
            "complete_horizon_count": flat_gate.complete_horizon_count,
            "checkpoint_sha256": flat_evidence.inventory.sha256,
            "checkpoint_effective_step": flat_evidence.inventory.effective_step,
        },
        "selected_step": FLAT_EFFECTIVE_STEPS if flat_gate.passed else None,
        "selected_checkpoint_step": FLAT_EFFECTIVE_STEPS if flat_gate.passed else None,
        "requested_effective_steps": flat_steps,
        "trained_effective_steps": flat_trained_steps,
        "outcome": "passed" if flat_gate.passed else "failed",
    }

    if not flat_gate.passed:
        # The exact final flat boundary is the only legal transition parent.
        artifacts = finalize_fn(
            str(flat_config_path),
            flat_run_id,
            runs_root,
            _finalize_overrides(overrides, flat_steps),
            matrix_digest=matrix_digest,
            phase_lineage={"flat": flat_phase_lineage, "rough": None},
        )
        return {
            "outcome": "NEEDS_HUMAN",
            "reason_code": "DERIVED_FLAT_GATE_FAILED",
            "phase_lineage": {"flat": flat_phase_lineage, "rough": None},
            "artifacts": artifacts,
        }

    selected_flat_inventory = flat_evidence.inventory
    flat_checkpoint_path = checkpoint_by_digest(flat_checkpoint_dir, selected_flat_inventory.sha256)

    # --- Phase 2: rough, resumed from the selected flat checkpoint. --------
    flat_effective_steps = selected_flat_inventory.effective_step
    remaining = rough_budget(
        FLAT_EFFECTIVE_STEPS,
        checkpoint_effective_step=flat_effective_steps,
        flat_trained_steps=flat_trained_steps,
    )
    raw_rough_config: RunConfig = load_config(rough_config_path, overrides)
    rough_steps = bounded_mjx_phase_steps(
        remaining,
        checkpoint_every_steps=raw_rough_config.checkpoint.every_steps,
        n_envs=raw_rough_config.training.n_envs,
        unroll_length=int(raw_rough_config.training.hyperparameters["unroll_length"]),
    )
    rough_config: RunConfig = load_config(
        rough_config_path, {**overrides, "training.total_steps": rough_steps}
    )
    if rough_config.environment != ROUGH_ENVIRONMENT:
        raise CurriculumError("rough config does not declare the reviewed rough environment")
    rough_run_id = f"{run_id}-rough"
    rough_paths = create_run_paths(rough_run_id, runs_root)
    flat_store = ArtifactStore(flat_config.storage, flat_run_id)
    rough_store = ArtifactStore(rough_config.storage, rough_run_id)
    trainer_load_path = str(rough_paths.root / "resume" / flat_checkpoint_path.stem)
    transition_record = build_transition_record(
        parent_checkpoint=flat_checkpoint_path,
        parent_object_key=flat_store.key_for(f"checkpoints/{flat_checkpoint_path.name}"),
        parent_sidecar_key=flat_store.key_for(
            f"checkpoints/{flat_checkpoint_path.with_suffix('.zip.json').name}"
        ),
        target_run_id=rough_run_id,
        trainer_load_path=trainer_load_path,
        matrix_digest=matrix_digest,
        image_digest=image_digest,
        flat_config_digest=flat_config_digest,
        rough_config_digest=_config_digest(rough_config_path),
        measured_flat_steps=flat_trained_steps,
        remaining_rough_budget=remaining,
        requested_rough_steps=rough_steps,
    )
    write_immutable_local(
        rough_paths.root / TRANSITION_RELATIVE_PATH, transition_record
    )
    rough_store.put_immutable_json(TRANSITION_RELATIVE_PATH, transition_record)
    verify_transition_record(
        transition_record,
        parent_checkpoint=flat_checkpoint_path,
        target_config=rough_config,
        matrix_digest=matrix_digest,
        image_digest=image_digest,
        flat_config_digest=flat_config_digest,
        rough_config_digest=_config_digest(rough_config_path),
        target_run_id=rough_run_id,
        trainer_load_path=trainer_load_path,
    )
    # The rough phase resumes a flat-terrain checkpoint on purpose: that transfer is
    # the curriculum. The resume guard rejects a checkpoint from another environment
    # by default, which is right for an ordinary resume, so the one crossing this
    # curriculum declares is named explicitly rather than the check being relaxed.
    rough_final_checkpoint = train_phase(
        rough_config,
        rough_run_id,
        runs_root,
        resume=flat_checkpoint_path,
        allowed_source_environment=FLAT_ENVIRONMENT,
        transition_record=transition_record,
    )
    rough_checkpoint_dir = create_run_paths(rough_run_id, runs_root).checkpoints
    rough_effective_steps = load_checkpoint_metadata(rough_final_checkpoint).step
    if rough_effective_steps > remaining:
        raise CurriculumError("rough training exceeded its remaining-step budget")
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
    if selected_rough.inventory.effective_step > rough_effective_steps:
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
        selected_flat_step=FLAT_EFFECTIVE_STEPS,
        flat_effective_steps=flat_effective_steps,
        flat_trained_steps=flat_trained_steps,
        rough_effective_steps=rough_effective_steps,
        rough_requested_steps=rough_steps,
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
            "requested_effective_steps": rough_steps,
            "trained_effective_steps": rough_effective_steps,
        },
        "provenance": provenance,
        "transition": transition_record,
    }

    # Persist exact pre-finalization evidence so a finalizer retry cannot rerun
    # the flat gate, reselect the parent, or synthesize a different lineage.
    phase_lineage_path = rough_paths.report / "g1-phase-lineage.json"
    phase_lineage_path.write_text(
        json.dumps(phase_lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    rough_store.upload_file(phase_lineage_path, "report/g1-phase-lineage.json")

    finalization_input = {
        "schema_version": 1,
        "rough_run_id": rough_run_id,
        "selected_checkpoint_digest": selected_rough.inventory.sha256,
        "transition": transition_record,
        "phase_lineage": phase_lineage,
        "seed_roles": {
            "selection": list(selection_seeds),
            "final": list(final_seeds),
        },
        "ranking_explanation": ranking_explanation,
        "acceptance_criteria": acceptance_criteria,
    }
    write_immutable_local(
        rough_paths.report / "g1-finalization-input.json", finalization_input
    )
    rough_store.put_immutable_json(
        "report/g1-finalization-input.json", finalization_input
    )

    artifacts = finalize_fn(
        str(rough_config_path),
        rough_run_id,
        runs_root,
        _finalize_overrides(overrides, rough_steps),
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


def _parse_overrides(items: Sequence[str]) -> dict[str, Any]:
    """Parse `--set key=value` pairs, refusing anything without exactly one `=`."""
    overrides: dict[str, Any] = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise CurriculumError(f"invalid --set override: {item}")
        overrides[key] = value
    _validate_overrides(overrides)
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the bounded G1 flat-to-rough curriculum")
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--flat-config", required=True)
    parser.add_argument("--rough-config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--image-digest", required=True)
    parser.add_argument(
        "--recover-existing",
        action="store_true",
        help="Reuse exact completed durable phase checkpoints and skip both training phases.",
    )
    parser.add_argument("--set", action="append", default=[])
    return parser


def _record_failure(args: Any, exc: BaseException) -> None:
    """Persist a sanitized crash record beside the run's other durable evidence.

    Best effort by construction: a failure here must never replace the real
    exception, which is the one worth seeing.
    """
    import traceback

    from sim2policy.storage import ArtifactStore

    try:
        config = load_config(args.flat_config, _parse_overrides(args.set))
        store = ArtifactStore(config.storage, args.run_id)
        store.put_json(
            "failure.json",
            {
                "run_id": args.run_id,
                "phase": "curriculum",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
    except Exception:  # noqa: BLE001 - diagnostics must not mask the real failure
        traceback.print_exc()


def main(argv: Sequence[str] | None = None) -> None:
    from sim2policy.execution_location import require_nebius_execution

    args = build_parser().parse_args(argv)
    require_nebius_execution("finalization" if args.recover_existing else "training")
    from sim2policy.showcase_matrix import load_matrix

    matrix = load_matrix(args.matrix)
    card = matrix.card("g1")
    campaign = matrix.campaign
    try:
        common = {
            "flat_config_path": args.flat_config,
            "rough_config_path": args.rough_config,
            "run_id": args.run_id,
            "runs_root": args.runs_root,
            "matrix_digest": matrix.digest,
            "image_digest": args.image_digest,
            "gallery_example_id": card["gallery_example_id"],
            "config_overrides": _parse_overrides(args.set),
        }
        result = recover_g1_finalization(**common) if args.recover_existing else run_g1_curriculum(
            **common,
            selection_seeds=campaign["selection"]["seeds"],
            final_seeds=campaign["final"]["seeds"],
            selection_episodes_per_seed=campaign["selection"]["episodes_per_seed"],
            final_episodes_per_seed=campaign["final"]["episodes_per_seed"],
            acceptance_criteria=card["acceptance"],
        )
    except BaseException as exc:  # noqa: BLE001 - recorded, then re-raised unchanged
        # The curriculum runs for hours on an H100 and the provider keeps no
        # readable container log, so an unrecorded crash is undiagnosable without
        # spending another hour to reproduce it. Persist the failure where
        # verification already looks, then let the original exception stand.
        _record_failure(args, exc)
        raise
    print(json.dumps({"outcome": result["outcome"]}, sort_keys=True))
    # The hosted process completed its declared work for every returned outcome.
    # Exit 20/30 belong to the campaign controller; using them inside a Nebius
    # workload turns a valid finalized rejection into provider ContainerFailed.
    # Only an exception before durable finalization should make the remote job fail.


if __name__ == "__main__":
    main()
