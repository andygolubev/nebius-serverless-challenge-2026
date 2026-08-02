from __future__ import annotations

import json
import subprocess
import sys

from sim2policy.finalize import _phase
from sim2policy.hosted_mjx import build_commands, run


def test_finalization_phase_events_are_machine_readable(capsys) -> None:
    _phase("upload_complete")
    assert json.loads(capsys.readouterr().out) == {
        "event": "finalization_phase",
        "phase": "upload_complete",
    }


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


def test_remote_resume_can_name_a_distinct_source_run() -> None:
    train, _finalize = build_commands(
        [
            "--config", "configs/g1_mjx.yaml", "--run-id", "rough-run",
            "--resume", "remote", "--resume-run-id", "flat-run",
        ]
    )
    assert train[train.index("--resume-run-id") + 1] == "flat-run"


def test_g1_transition_evidence_is_passed_to_training_only() -> None:
    train, finalize = build_commands(
        [
            "--config", "configs/g1_forward_rough_mjx.yaml",
            "--run-id", "rough-run",
            "--resume", "remote",
            "--resume-run-id", "flat-run",
            "--g1-transition-source-config", "configs/g1_forward_flat_mjx.yaml",
            "--g1-transition-matrix-digest", "matrix-digest",
            "--g1-transition-image-digest", "sha256:image",
            "--g1-transition-remaining-budget", "163840",
        ]
    )
    assert train[train.index("--g1-transition-source-config") + 1] == (
        "configs/g1_forward_flat_mjx.yaml"
    )
    assert train[train.index("--g1-transition-remaining-budget") + 1] == "163840"
    assert "--g1-transition-source-config" not in finalize


def test_resume_is_absent_unless_requested() -> None:
    train, _finalize = build_commands(["--config", "c.yaml", "--run-id", "r1"])
    assert "--resume" not in train


def test_hosted_mjx_forwards_curation_evidence_to_finalization_only() -> None:
    """The campaign emits these for every example, so MJX must accept them too.

    Go1 died in under a second because argparse rejected flags the SB3 entrypoint
    already understood; the two entrypoints share one campaign command builder and
    must therefore share this argument surface.
    """
    train, finalize = build_commands(
        [
            "--config",
            "configs/go1_mjx.yaml",
            "--run-id",
            "run-safe",
            "--gallery-example-id",
            "go1-walker",
            "--seed-roles-json",
            '{"training": [0], "selection": [101], "final": [0]}',
            "--ranking-explanation-json",
            '{"kind": "locomotion"}',
            "--acceptance-criteria-json",
            '{"hard": {"min_velocity": 0.5, "no_fall": true}}',
        ]
    )
    assert "--seed-roles-json" not in train
    assert finalize[finalize.index("--seed-roles-json") + 1] == (
        '{"training": [0], "selection": [101], "final": [0]}'
    )
    assert finalize[finalize.index("--ranking-explanation-json") + 1] == '{"kind": "locomotion"}'
    assert "--acceptance-criteria-json" in finalize


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
    assert calls[1][1]["timeout"] == 2700
