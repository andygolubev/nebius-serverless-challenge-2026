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


def build_commands(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    parser = argparse.ArgumentParser(description="Run hosted MJX training and finalization")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--gallery-example-id")
    parser.add_argument("--selected-checkpoint-digest")
    parser.add_argument("--matrix-digest")
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument(
        "--resume",
        nargs="?",
        const="latest",
        help="Resume training: 'remote' pulls this run's latest durable checkpoint.",
    )
    parser.add_argument("--resume-run-id", help="Source run ID for --resume remote.")
    parser.add_argument("--set", action="append", default=[])
    args = parser.parse_args(argv)

    shared = ["--config", args.config, "--run-id", args.run_id, "--runs-root", args.runs_root]
    overrides = [value for item in args.set for value in ("--set", item)]
    # Resume is a training-only concern; finalization always works from the run
    # tree the training phase leaves behind.
    resume = ["--resume", args.resume] if args.resume else []
    if args.resume_run_id:
        resume += ["--resume-run-id", args.resume_run_id]
    train = [sys.executable, "-m", "sim2policy.train_mjx", *shared, *resume, *overrides]
    finalize = [sys.executable, "-m", "sim2policy.finalize", *shared]
    if args.gallery_example_id:
        finalize += ["--gallery-example-id", args.gallery_example_id]
    if args.selected_checkpoint_digest:
        finalize += ["--selected-checkpoint-digest", args.selected_checkpoint_digest]
    if args.matrix_digest:
        finalize += ["--matrix-digest", args.matrix_digest]
    finalize += overrides
    return train, finalize


def run(
    argv: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    train, finalize = build_commands(argv)
    runner(train, check=True, text=True)
    environment = os.environ.copy()
    environment["SIM2POLICY_COMMAND_CLASS"] = "finalization"
    runner(finalize, check=True, text=True, env=environment)


def main(argv: Sequence[str] | None = None) -> None:
    from sim2policy.execution_location import require_nebius_execution

    require_nebius_execution("training")
    run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    main()
