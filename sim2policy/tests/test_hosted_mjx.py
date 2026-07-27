from __future__ import annotations

import subprocess
import sys

from sim2policy.hosted_mjx import build_commands, run


def test_commands_keep_validated_arguments_as_array_elements() -> None:
    train, finalize = build_commands(
        [
            "--config", "configs/go1_mjx.yaml",
            "--run-id", "run-safe-1",
            "--set", "training.total_steps=5000000",
            "--set", "storage.mode=s3",
        ]
    )
    assert train[:3] == [sys.executable, "-m", "sim2policy.train_mjx"]
    assert finalize[:3] == [sys.executable, "-m", "sim2policy.finalize"]
    assert "run-safe-1" in train and "run-safe-1" in finalize
    assert train.count("--set") == 2 and finalize.count("--set") == 2


def test_resume_is_passed_to_training_only() -> None:
    """Finalization works from the run tree; only training resumes a checkpoint."""
    train, finalize = build_commands(
        ["--config", "configs/g1_flat_mjx.yaml", "--run-id", "run-safe-1", "--resume", "remote"]
    )
    assert train[train.index("--resume") + 1] == "remote"
    assert "--resume" not in finalize


def test_resume_is_absent_unless_requested() -> None:
    train, _finalize = build_commands(["--config", "c.yaml", "--run-id", "r1"])
    assert "--resume" not in train


def test_run_trains_then_finalizes_in_separate_processes() -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    run(["--config", "c.yaml", "--run-id", "r1"], runner=runner)
    assert [call[0][2] for call in calls] == ["sim2policy.train_mjx", "sim2policy.finalize"]
    assert calls[0][1] == {"check": True, "text": True}
    assert calls[1][1]["check"] is True and calls[1][1]["text"] is True
    assert calls[1][1]["env"]["SIM2POLICY_COMMAND_CLASS"] == "finalization"
