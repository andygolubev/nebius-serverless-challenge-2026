"""End-to-end hosted MJX job: train, release the process, then finalize artifacts.

The SaaS catalog invokes this fixed module with validated arguments. Training and
finalization run in separate child processes so JAX/XLA allocations from training
cannot leak into evaluation and rendering.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence

FINALIZE_TIMEOUT_ENVIRONMENT_VARIABLE = "SIM2POLICY_FINALIZE_TIMEOUT_SECONDS"
# A cold G1 MJX render takes about four minutes on the verified H100 image, and
# finalization deliberately renders four independently isolated checkpoints.
# Fifteen minutes therefore aborts a healthy run before evaluation/upload; keep
# the guard below the one-hour smoke provider limit while covering that measured
# workload.
DEFAULT_FINALIZE_TIMEOUT_SECONDS = 2700


def _finalize_timeout_seconds(environment: dict[str, str]) -> int:
    value = environment.get(FINALIZE_TIMEOUT_ENVIRONMENT_VARIABLE, "")
    if not value:
        return DEFAULT_FINALIZE_TIMEOUT_SECONDS
    try:
        timeout = int(value)
    except ValueError as exc:
        raise ValueError(f"{FINALIZE_TIMEOUT_ENVIRONMENT_VARIABLE} must be an integer") from exc
    if timeout <= 0:
        raise ValueError(f"{FINALIZE_TIMEOUT_ENVIRONMENT_VARIABLE} must be positive")
    return timeout


def build_commands(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    parser = argparse.ArgumentParser(description="Run hosted MJX training and finalization")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--gallery-example-id")
    parser.add_argument("--selected-checkpoint-digest")
    parser.add_argument("--matrix-digest")
    # Curation evidence the campaign owns and the finalizer records verbatim; the
    # job never invents these, and without them a run cannot be accepted.
    parser.add_argument("--seed-roles-json")
    parser.add_argument("--ranking-explanation-json")
    parser.add_argument("--acceptance-criteria-json")
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument(
        "--resume",
        nargs="?",
        const="latest",
        help="Resume training: 'remote' pulls this run's latest durable checkpoint.",
    )
    parser.add_argument("--resume-run-id", help="Source run ID for --resume remote.")
    parser.add_argument("--g1-transition-source-config")
    parser.add_argument("--g1-transition-matrix-digest")
    parser.add_argument("--g1-transition-image-digest")
    parser.add_argument("--g1-transition-remaining-budget", type=int)
    parser.add_argument("--set", action="append", default=[])
    args = parser.parse_args(argv)

    shared = ["--config", args.config, "--run-id", args.run_id, "--runs-root", args.runs_root]
    overrides = [value for item in args.set for value in ("--set", item)]
    # Resume is a training-only concern; finalization always works from the run
    # tree the training phase leaves behind.
    resume = ["--resume", args.resume] if args.resume else []
    if args.resume_run_id:
        resume += ["--resume-run-id", args.resume_run_id]
    for flag, value in (
        ("--g1-transition-source-config", args.g1_transition_source_config),
        ("--g1-transition-matrix-digest", args.g1_transition_matrix_digest),
        ("--g1-transition-image-digest", args.g1_transition_image_digest),
        ("--g1-transition-remaining-budget", args.g1_transition_remaining_budget),
    ):
        if value is not None:
            resume += [flag, str(value)]
    train = [sys.executable, "-m", "sim2policy.train_mjx", *shared, *resume, *overrides]
    finalize = [sys.executable, "-m", "sim2policy.finalize", *shared]
    if args.gallery_example_id:
        finalize += ["--gallery-example-id", args.gallery_example_id]
    if args.selected_checkpoint_digest:
        finalize += ["--selected-checkpoint-digest", args.selected_checkpoint_digest]
    if args.matrix_digest:
        finalize += ["--matrix-digest", args.matrix_digest]
    for flag, value in (
        ("--seed-roles-json", args.seed_roles_json),
        ("--ranking-explanation-json", args.ranking_explanation_json),
        ("--acceptance-criteria-json", args.acceptance_criteria_json),
    ):
        if value:
            finalize += [flag, value]
    finalize += overrides
    return train, finalize


def run(
    argv: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    train, finalize = build_commands(argv)
    print('{"event":"phase","phase":"training_start"}', flush=True)
    runner(train, check=True, text=True)
    print('{"event":"phase","phase":"training_complete"}', flush=True)
    environment = os.environ.copy()
    environment["SIM2POLICY_COMMAND_CLASS"] = "finalization"
    timeout = _finalize_timeout_seconds(environment)
    print('{"event":"phase","phase":"finalization_start"}', flush=True)
    try:
        runner(finalize, check=True, text=True, env=environment, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        print('{"event":"phase","phase":"finalization_timeout"}', flush=True)
        raise RuntimeError(f"finalization exceeded {timeout} seconds") from exc
    print('{"event":"phase","phase":"finalization_complete"}', flush=True)


def main(argv: Sequence[str] | None = None) -> None:
    from sim2policy.execution_location import require_nebius_execution

    require_nebius_execution("training")
    run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    main()
