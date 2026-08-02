from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from sim2policy.checkpoint import checkpoint_inventory, checkpoint_path, write_checkpoint_metadata
from sim2policy.checkpoint_selection import EvaluationEvidence
from sim2policy.config import RunConfig
from sim2policy.g1_curriculum import FLAT_EFFECTIVE_STEPS
from sim2policy.hosted_g1_curriculum import (
    recover_g1_finalization,
    run_g1_curriculum,
)
from sim2policy.run import create_run_paths

ROOT = Path(__file__).parents[1]
FLAT_CONFIG = ROOT / "configs/g1_forward_flat_mjx.yaml"
ROUGH_CONFIG = ROOT / "configs/g1_forward_rough_mjx.yaml"
SELECTION_SEEDS = (101, 151, 211, 271, 331)
FINAL_SEEDS = (0, 1, 2, 3, 4)
ACCEPTANCE = {
    "hard": {"episodes": 20, "no_fall": True, "min_velocity": 0.4},
    "preferred": {
        "episodes": 20,
        "no_fall": True,
        "min_velocity": 0.4,
        "mean_velocity": 0.6,
    },
}


def _write_checkpoint(directory: Path, config: RunConfig, kind: str, step: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = checkpoint_path(directory, kind, step)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("policy.bin", f"fake-{step}".encode())
    write_checkpoint_metadata(path, config, step)
    return path


def _episodes(
    seeds: tuple[int, ...], episodes_per_seed: int, velocity: float = 0.7
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "seed": seed,
            "reward": 1.0,
            "length": 1000,
            "mean_velocity": velocity,
            "fell": False,
            "terminated": False,
            "termination_reason": "horizon",
            "termination_causes": ["horizon"],
        }
        for seed in seeds
        for _ in range(episodes_per_seed)
    )


def test_fresh_curriculum_gates_only_derived_final_and_records_transition(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def train(
        config: RunConfig,
        run_id: str,
        runs_root: Path,
        resume: Path | None = None,
        **kwargs: Any,
    ) -> Path:
        calls.append({"config": config, "run_id": run_id, "resume": resume, **kwargs})
        directory = create_run_paths(run_id, runs_root).checkpoints
        if resume is None:
            _write_checkpoint(directory, config, "step", 25_000_000)
            return _write_checkpoint(directory, config, "final", FLAT_EFFECTIVE_STEPS)
        _write_checkpoint(directory, config, "step", 25_000_000)
        return _write_checkpoint(directory, config, "final", config.training.total_steps)

    def evaluate_candidates_fn(
        checkpoints,
        config,
        *,
        run_lineage,
        selection_seeds,
        final_seeds,
        episodes_per_seed,
        phase,
    ):
        return [
            EvaluationEvidence(
                checkpoint_inventory(path, config, run_lineage=run_lineage, phase=phase),
                "selection",
                tuple(selection_seeds),
                _episodes(tuple(selection_seeds), episodes_per_seed),
                1.0,
                "locomotion",
            )
            for path in checkpoints
        ]

    def evaluate_final_fn(
        checkpoint,
        config,
        *,
        run_lineage,
        selection_seeds,
        final_seeds,
        episodes_per_seed,
    ):
        return EvaluationEvidence(
            checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase="selected"),
            "final",
            tuple(final_seeds),
            _episodes(tuple(final_seeds), episodes_per_seed),
            1.0,
            "locomotion",
        )

    finalized: list[dict[str, Any]] = []

    def finalize(*args: Any, **kwargs: Any) -> dict[str, str]:
        finalized.append(kwargs)
        return {"metrics_json": "report/metrics.json"}

    result = run_g1_curriculum(
        flat_config_path=FLAT_CONFIG,
        rough_config_path=ROUGH_CONFIG,
        run_id="g1-fresh",
        runs_root=tmp_path,
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        gallery_example_id="g1-rough-terrain",
        selection_seeds=SELECTION_SEEDS,
        final_seeds=FINAL_SEEDS,
        selection_episodes_per_seed=2,
        final_episodes_per_seed=4,
        acceptance_criteria=ACCEPTANCE,
        train_phase=train,
        evaluate_candidates_fn=evaluate_candidates_fn,
        evaluate_final_fn=evaluate_final_fn,
        finalize_fn=finalize,
    )

    assert result["outcome"] == "ACCEPTED"
    assert len(calls) == 2
    assert calls[0]["config"].training.total_steps == FLAT_EFFECTIVE_STEPS
    assert calls[1]["allowed_source_environment"] == "G1ForwardFlatTerrain"
    transition = calls[1]["transition_record"]
    assert transition["parent"]["sidecar_step"] == FLAT_EFFECTIVE_STEPS
    assert transition["restore"]["fresh_initialization_seed"] == 0
    assert transition["restore"]["reinitialized_components"] == [
        "optimizer_state",
        "learner_step",
        "rollout_state",
        "prng_state",
    ]
    durable = tmp_path / "g1-fresh-rough/report/g1-transition.json"
    assert json.loads(durable.read_text()) == transition
    assert finalized[0]["phase_lineage"]["transition"] == transition


def test_failed_derived_flat_gate_stops_before_transition(tmp_path: Path) -> None:
    def train(config: RunConfig, run_id: str, runs_root: Path, **kwargs: Any) -> Path:
        del kwargs
        return _write_checkpoint(
            create_run_paths(run_id, runs_root).checkpoints,
            config,
            "final",
            FLAT_EFFECTIVE_STEPS,
        )

    def evaluate_candidates_fn(
        checkpoints,
        config,
        *,
        run_lineage,
        selection_seeds,
        final_seeds,
        episodes_per_seed,
        phase,
    ):
        episodes = list(_episodes(tuple(selection_seeds), episodes_per_seed))
        episodes[0].update(
            fell=True,
            terminated=True,
            length=900,
            termination_reason="foot_shin_contact",
            termination_causes=["foot_shin_contact"],
        )
        return [
            EvaluationEvidence(
                checkpoint_inventory(checkpoints[0], config, run_lineage=run_lineage, phase=phase),
                "selection",
                tuple(selection_seeds),
                tuple(episodes),
                1.0,
                "locomotion",
            )
        ]

    finalized: list[dict[str, Any]] = []
    result = run_g1_curriculum(
        flat_config_path=FLAT_CONFIG,
        rough_config_path=ROUGH_CONFIG,
        run_id="g1-flat-fails",
        runs_root=tmp_path,
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        gallery_example_id="g1-rough-terrain",
        selection_seeds=SELECTION_SEEDS,
        final_seeds=FINAL_SEEDS,
        selection_episodes_per_seed=2,
        final_episodes_per_seed=4,
        acceptance_criteria=ACCEPTANCE,
        train_phase=train,
        evaluate_candidates_fn=evaluate_candidates_fn,
        finalize_fn=lambda *args, **kwargs: finalized.append(kwargs) or {},
    )
    assert result["outcome"] == "NEEDS_HUMAN"
    assert result["reason_code"] == "DERIVED_FLAT_GATE_FAILED"
    assert not (tmp_path / "g1-flat-fails-rough").exists()
    assert len(finalized) == 1


def test_recovery_refuses_missing_immutable_transition(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="transition or finalization input"):
        recover_g1_finalization(
            flat_config_path=FLAT_CONFIG,
            rough_config_path=ROUGH_CONFIG,
            run_id="g1-recover",
            runs_root=tmp_path,
            matrix_digest="a" * 64,
            image_digest="sha256:" + "b" * 64,
            gallery_example_id="g1-rough-terrain",
            config_overrides={},
        )
