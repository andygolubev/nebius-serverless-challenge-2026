"""End-to-end hosted SB3 job with a fixed train-then-finalize boundary."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence


def build_commands(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    parser = argparse.ArgumentParser(description="Run hosted SB3 training and finalization")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--gallery-example-id", required=True)
    parser.add_argument("--selected-checkpoint-digest")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--resume-checkpoint-path")
    parser.add_argument("--resume-checkpoint-sha256")
    parser.add_argument("--matrix-digest")
    # Curation evidence the campaign owns and the finalizer records verbatim; the
    # job never invents these, and without them a run cannot be accepted.
    parser.add_argument("--seed-roles-json")
    parser.add_argument("--ranking-explanation-json")
    parser.add_argument("--acceptance-criteria-json")
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument("--set", action="append", default=[])
    args = parser.parse_args(argv)

    shared = ["--config", args.config, "--run-id", args.run_id, "--runs-root", args.runs_root]
    overrides = [value for item in args.set for value in ("--set", item)]
    train = [sys.executable, "-m", "sim2policy.train_sb3", *shared, *overrides]
    finalize = [
        sys.executable,
        "-m",
        "sim2policy.finalize",
        *shared,
        "--gallery-example-id",
        args.gallery_example_id,
        *overrides,
    ]
    for flag, value in (
        ("--resume-run-id", args.resume_run_id),
        ("--resume-checkpoint-path", args.resume_checkpoint_path),
        ("--resume-checkpoint-sha256", args.resume_checkpoint_sha256),
    ):
        if value:
            train += [flag, value]
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
