from __future__ import annotations

import sys

import pytest

from sim2policy.hosted_sb3 import build_commands, run


def test_hosted_sb3_builds_fixed_train_then_gallery_finalize_commands() -> None:
    train, finalize = build_commands(
        [
            "--config",
            "configs/hopper_sb3.yaml",
            "--run-id",
            "run-safe",
            "--gallery-example-id",
            "hopper-balance",
            "--set",
            "seed=7",
        ]
    )
    assert train[:3] == [sys.executable, "-m", "sim2policy.train_sb3"]
    assert finalize[:3] == [sys.executable, "-m", "sim2policy.finalize"]
    assert "--gallery-example-id" not in train
    assert finalize[finalize.index("--gallery-example-id") + 1] == "hopper-balance"
    assert "seed=7" in train and "seed=7" in finalize


def test_hosted_sb3_stops_before_finalization_when_training_fails() -> None:
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append(command)
        raise RuntimeError("training failed")

    with pytest.raises(RuntimeError, match="training failed"):
        run(
            [
                "--config",
                "configs/hopper_sb3.yaml",
                "--run-id",
                "run-safe",
                "--gallery-example-id",
                "hopper-balance",
            ],
            runner=runner,
        )
    assert len(calls) == 1
    assert "sim2policy.train_sb3" in calls[0]


def test_hosted_sb3_forwards_curation_evidence_to_finalization_only() -> None:
    """Training does not need seed roles or thresholds; publication does."""
    train, finalize = build_commands(
        [
            "--config",
            "configs/hopper_sb3.yaml",
            "--run-id",
            "run-safe",
            "--gallery-example-id",
            "hopper-balance",
            "--seed-roles-json",
            '{"training": [7], "selection": [101], "final": [0]}',
            "--ranking-explanation-json",
            '{"kind": "mean_reward"}',
            "--acceptance-criteria-json",
            '{"hard": {"mean_reward": 1000}, "preferred": {"mean_reward": 1800}}',
        ]
    )
    assert "--seed-roles-json" not in train
    assert finalize[finalize.index("--seed-roles-json") + 1] == (
        '{"training": [7], "selection": [101], "final": [0]}'
    )
    assert finalize[finalize.index("--ranking-explanation-json") + 1] == '{"kind": "mean_reward"}'
    assert "--acceptance-criteria-json" in finalize


def test_hosted_sb3_resumes_only_training_from_an_exact_parent_checkpoint() -> None:
    train, finalize = build_commands(
        [
            "--config", "configs/hopper_sb3.yaml", "--run-id", "child",
            "--gallery-example-id", "hopper-balance", "--resume-run-id", "parent",
            "--resume-checkpoint-path", "step-000003000000.zip",
            "--resume-checkpoint-sha256", "a" * 64,
        ]
    )
    assert train[train.index("--resume-run-id") + 1] == "parent"
    assert "--resume-run-id" not in finalize
