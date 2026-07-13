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


def test_run_trains_then_finalizes_in_separate_processes() -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    run(["--config", "c.yaml", "--run-id", "r1"], runner=runner)
    assert [call[0][2] for call in calls] == ["sim2policy.train_mjx", "sim2policy.finalize"]
    assert all(call[1] == {"check": True, "text": True} for call in calls)
