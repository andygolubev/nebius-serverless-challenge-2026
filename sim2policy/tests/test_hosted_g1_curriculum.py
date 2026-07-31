# ruff: noqa: E501

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from sim2policy.checkpoint import checkpoint_inventory, checkpoint_path, write_checkpoint_metadata
from sim2policy.checkpoint_selection import EvaluationEvidence
from sim2policy.config import RunConfig, load_config
from sim2policy.g1_curriculum import rough_budget
from sim2policy.hosted_g1_curriculum import run_g1_curriculum
from sim2policy.run import create_run_paths

ROOT = Path(__file__).parents[1]
FLAT_CONFIG = ROOT / "configs/g1_flat_mjx.yaml"
ROUGH_CONFIG = ROOT / "configs/g1_mjx.yaml"
SELECTION_SEEDS = (101, 151, 211, 271, 331)
FINAL_SEEDS = (0, 1, 2, 3, 4)
ACCEPTANCE_CRITERIA = {
    "hard": {"episodes": len(FINAL_SEEDS), "no_fall": True, "min_velocity": 0.4},
    "preferred": {
        "episodes": len(FINAL_SEEDS),
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


def _episodes(seeds: tuple[int, ...], *, reward: float, velocity: float, fell: bool) -> tuple[dict[str, Any], ...]:
    return tuple(
        {"seed": seed, "reward": reward, "length": 1000, "mean_velocity": velocity, "fell": fell}
        for seed in seeds
    )


def test_never_passing_flat_gate_stops_before_rough_and_records_diagnostics(tmp_path: Path) -> None:
    train_calls: list[tuple[str, Path | None]] = []

    def fake_train_phase(config: RunConfig, run_id: str, runs_root: Path, resume: Path | None = None, **kwargs: Any) -> Path:
        train_calls.append((run_id, resume))
        directory = create_run_paths(run_id, runs_root).checkpoints
        for step in (100_000_000, 150_000_000, 200_000_000):
            _write_checkpoint(directory, config, "step", step)
        return directory / "step-000200000000.zip"

    def fake_evaluate_candidates(checkpoints, config, *, run_lineage, selection_seeds, final_seeds, episodes_per_seed, phase):
        return [
            EvaluationEvidence(
                checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase=phase),
                "selection",
                tuple(selection_seeds),
                _episodes(tuple(selection_seeds), reward=0.0, velocity=0.0, fell=False),
                1.0,
                "test",
            )
            for checkpoint in checkpoints
        ]

    finalize_calls: list[dict[str, Any]] = []

    def fake_finalize(config_path, run_id, runs_root, overrides, **kwargs):
        finalize_calls.append({"run_id": run_id, **kwargs})
        return {"metrics_json": "report/metrics.json"}

    result = run_g1_curriculum(
        flat_config_path=FLAT_CONFIG,
        rough_config_path=ROUGH_CONFIG,
        run_id="g1-never-passes",
        runs_root=tmp_path,
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        gallery_example_id="g1-rough-terrain",
        selection_seeds=SELECTION_SEEDS,
        final_seeds=FINAL_SEEDS,
        selection_episodes_per_seed=2,
        final_episodes_per_seed=4,
        acceptance_criteria=ACCEPTANCE_CRITERIA,
        train_phase=fake_train_phase,
        evaluate_candidates_fn=fake_evaluate_candidates,
        finalize_fn=fake_finalize,
    )

    assert result["outcome"] == "NEEDS_HUMAN"
    assert result["reason_code"] == "FLAT_GATE_NEVER_PASSED"
    assert result["phase_lineage"]["rough"] is None
    # Rough training is never started when no flat gate passes.
    assert train_calls == [("g1-never-passes-flat", None)]
    assert len(finalize_calls) == 1
    assert "gallery_example_id" not in finalize_calls[0]


def test_a_later_gate_passing_shortens_the_rough_budget_by_exactly_its_step(tmp_path: Path) -> None:
    """The 100M gate fails, 150M passes: rough gets 450M - 150M, not 450M - 100M."""
    train_calls: list[tuple[str, Path | None]] = []

    def fake_train_phase(config: RunConfig, run_id: str, runs_root: Path, resume: Path | None = None, **kwargs: Any) -> Path:
        train_calls.append((run_id, resume))
        directory = create_run_paths(run_id, runs_root).checkpoints
        if resume is None:
            for step in (100_000_000, 150_000_000, 200_000_000):
                _write_checkpoint(directory, config, "step", step)
            return directory / "step-000200000000.zip"
        _write_checkpoint(directory, config, "final", 300_000_000)
        return directory / "final-000300000000.zip"

    def fake_evaluate_candidates(checkpoints, config, *, run_lineage, selection_seeds, final_seeds, episodes_per_seed, phase):
        result = []
        for checkpoint in checkpoints:
            inventory = checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase=phase)
            # Only the 150M flat checkpoint walks; 100M still falls.
            if phase == "flat" and inventory.effective_step < 150_000_000:
                episodes = _episodes(tuple(selection_seeds), reward=1.0, velocity=0.5, fell=True)
            else:
                episodes = _episodes(tuple(selection_seeds), reward=1.0, velocity=0.7, fell=False)
            result.append(
                EvaluationEvidence(inventory, "selection", tuple(selection_seeds), episodes, 1.0, "test")
            )
        return result

    def fake_evaluate_final(checkpoint, config, *, run_lineage, selection_seeds, final_seeds, episodes_per_seed):
        inventory = checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase="selected")
        return EvaluationEvidence(
            inventory, "final", tuple(final_seeds),
            _episodes(tuple(final_seeds), reward=1.0, velocity=0.7, fell=False), 1.0, "test",
        )

    finalize_calls: list[dict[str, Any]] = []

    def fake_finalize(config_path, run_id, runs_root, overrides, **kwargs):
        finalize_calls.append({"run_id": run_id, "overrides": overrides, **kwargs})
        return {"metrics_json": "report/metrics.json"}

    result = run_g1_curriculum(
        flat_config_path=FLAT_CONFIG,
        rough_config_path=ROUGH_CONFIG,
        run_id="g1-late-gate",
        runs_root=tmp_path,
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        gallery_example_id="g1-rough-terrain",
        selection_seeds=SELECTION_SEEDS,
        final_seeds=FINAL_SEEDS,
        selection_episodes_per_seed=2,
        final_episodes_per_seed=4,
        acceptance_criteria=ACCEPTANCE_CRITERIA,
        train_phase=fake_train_phase,
        evaluate_candidates_fn=fake_evaluate_candidates,
        evaluate_final_fn=fake_evaluate_final,
        finalize_fn=fake_finalize,
    )

    lineage = result["phase_lineage"]
    assert lineage["flat"]["selected_step"] == 150_000_000
    # The 100M gate was measured and failed; both are retained as honest evidence.
    assert [item["step"] for item in lineage["flat"]["gates"]] == [100_000_000, 150_000_000]
    assert [item["passed"] for item in lineage["flat"]["gates"]] == [False, True]
    assert lineage["rough"]["budget_effective_steps"] == rough_budget(150_000_000) == 300_000_000
    # The whole remaining budget was spent and the 450M ceiling is exactly met.
    assert lineage["provenance"]["measured_total_steps"] == 450_000_000
    assert finalize_calls[0]["overrides"] == [("training.total_steps", 300_000_000)]


def test_earliest_passing_flat_gate_resumes_rough_and_selects_stable_checkpoint(tmp_path: Path) -> None:
    train_calls: list[tuple[str, Path | None]] = []

    def fake_train_phase(config: RunConfig, run_id: str, runs_root: Path, resume: Path | None = None, **kwargs: Any) -> Path:
        train_calls.append((run_id, resume))
        directory = create_run_paths(run_id, runs_root).checkpoints
        if resume is None:
            _write_checkpoint(directory, config, "final", 100_000_000)
            return directory / "final-000100000000.zip"
        _write_checkpoint(directory, config, "step", 25_000_000)
        _write_checkpoint(directory, config, "final", 50_000_000)
        return directory / "final-000050000000.zip"

    def fake_evaluate_candidates(checkpoints, config, *, run_lineage, selection_seeds, final_seeds, episodes_per_seed, phase):
        result = []
        for checkpoint in checkpoints:
            inventory = checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase=phase)
            if phase == "flat":
                episodes = _episodes(tuple(selection_seeds), reward=1.0, velocity=0.5, fell=False)
            elif inventory.effective_step == 25_000_000:
                episodes = _episodes(tuple(selection_seeds), reward=1.0, velocity=0.6, fell=False)
            else:  # the later "final" candidate regresses and falls
                episodes = _episodes(tuple(selection_seeds), reward=99.0, velocity=0.6, fell=True)
            result.append(
                EvaluationEvidence(inventory, "selection", tuple(selection_seeds), episodes, 1.0, "test")
            )
        return result

    def fake_evaluate_final(checkpoint, config, *, run_lineage, selection_seeds, final_seeds, episodes_per_seed):
        inventory = checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase="selected")
        episodes = _episodes(tuple(final_seeds), reward=1.0, velocity=0.65, fell=False)
        return EvaluationEvidence(inventory, "final", tuple(final_seeds), episodes, 1.0, "test")

    finalize_calls: list[dict[str, Any]] = []

    def fake_finalize(config_path, run_id, runs_root, overrides, **kwargs):
        finalize_calls.append({"run_id": run_id, "overrides": overrides, **kwargs})
        return {"metrics_json": "report/metrics.json", "policy_bundle": "bundle/policy-bundle.zip"}

    result = run_g1_curriculum(
        flat_config_path=FLAT_CONFIG,
        rough_config_path=ROUGH_CONFIG,
        run_id="g1-passes",
        runs_root=tmp_path,
        matrix_digest="a" * 64,
        image_digest="sha256:" + "b" * 64,
        gallery_example_id="g1-rough-terrain",
        selection_seeds=SELECTION_SEEDS,
        final_seeds=FINAL_SEEDS,
        selection_episodes_per_seed=2,
        final_episodes_per_seed=4,
        acceptance_criteria=ACCEPTANCE_CRITERIA,
        train_phase=fake_train_phase,
        evaluate_candidates_fn=fake_evaluate_candidates,
        evaluate_final_fn=fake_evaluate_final,
        finalize_fn=fake_finalize,
    )

    assert result["outcome"] == "ACCEPTED"
    # Exactly one flat call (no resume) and one rough call (resumed from the
    # selected flat checkpoint) -- never a second seed or a retry.
    assert [call[0] for call in train_calls] == ["g1-passes-flat", "g1-passes-rough"]
    assert train_calls[1][1] is not None and train_calls[1][1].name == "final-000100000000.zip"

    remaining = rough_budget(100_000_000)
    assert result["phase_lineage"]["rough"]["budget_effective_steps"] == remaining
    assert result["phase_lineage"]["rough"]["selected_checkpoint_step"] == 25_000_000
    assert result["phase_lineage"]["provenance"]["rough"]["effective_steps"] == 25_000_000
    assert result["phase_lineage"]["provenance"]["measured_total_steps"] == 100_000_000 + 25_000_000

    assert len(finalize_calls) == 1
    call = finalize_calls[0]
    assert call["gallery_example_id"] == "g1-rough-terrain"
    # The stable 25M candidate is selected over the higher-reward but fallen
    # 50M candidate -- stability outranks reward, exactly as locomotion
    # ranking requires.
    selected_inventory = checkpoint_inventory(
        checkpoint_path(create_run_paths("g1-passes-rough", tmp_path).checkpoints, "step", 25_000_000),
        load_config(ROUGH_CONFIG, {"training.total_steps": remaining}),
        run_lineage="g1-passes-rough",
    )
    assert call["selected_checkpoint_digest"] == selected_inventory.sha256
    assert call["seed_roles"] == {"selection": list(SELECTION_SEEDS), "final": list(FINAL_SEEDS)}
    assert call["ranking_explanation"]["kind"] == "locomotion"
    assert call["ranking_explanation"]["selected"]["effective_step"] == 25_000_000


def test_a_curriculum_crash_is_recorded_durably_and_still_raises(monkeypatch, tmp_path) -> None:
    """An H100 crash with no readable container log must leave a durable trace.

    The recorded failure is a diagnostic, never a substitute: the original
    exception has to reach the provider so the job still fails.
    """
    import sim2policy.hosted_g1_curriculum as hosted

    written: dict[str, Any] = {}

    class FakeStore:
        def __init__(self, _config: Any, run_id: str) -> None:
            written["run_id"] = run_id

        def put_json(self, relative: str, payload: dict[str, Any]) -> str:
            written["relative"] = relative
            written["payload"] = payload
            return relative

    monkeypatch.setattr("sim2policy.storage.ArtifactStore", FakeStore)
    monkeypatch.setattr(
        hosted, "run_g1_curriculum", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("xla ran out of memory"))
    )
    monkeypatch.setenv("SIM2POLICY_EXECUTION_LOCATION", "nebius")
    monkeypatch.setenv("SIM2POLICY_COMMAND_CLASS", "training")
    monkeypatch.setenv("SIM2POLICY_NEBIUS_RESOURCE_ID", "showcase-g1-crash")
    monkeypatch.setenv("SIM2POLICY_NEBIUS_REGION", "eu-north1")
    monkeypatch.setenv("SIM2POLICY_IMMUTABLE_REVISION", "git:" + "a" * 40)

    argv = [
        "--matrix", str(ROOT / "configs/showcase_training_matrix.yaml"),
        "--flat-config", str(FLAT_CONFIG),
        "--rough-config", str(ROUGH_CONFIG),
        "--run-id", "showcase-g1-crash",
        "--runs-root", str(tmp_path),
        "--image-digest", "sha256:" + "b" * 64,
    ]
    try:
        hosted.main(argv)
    except RuntimeError as exc:
        assert "xla ran out of memory" in str(exc)
    else:  # pragma: no cover - the crash must not be swallowed
        raise AssertionError("the original exception did not propagate")

    assert written["relative"] == "failure.json"
    assert written["payload"]["error_type"] == "RuntimeError"
    assert "xla ran out of memory" in written["payload"]["traceback"]


def test_rough_resume_declares_the_flat_environment_it_transfers_from(tmp_path: Path) -> None:
    """The curriculum's whole point is a flat->rough transfer across environments.

    `train_mjx` refuses a resume from a different environment unless the caller
    names it. Omitting that killed three H100 attempts after the flat phase had
    already trained 200M steps: the crossing has to be declared, not assumed.
    """
    calls: list[dict[str, Any]] = []

    def fake_train_phase(config: RunConfig, run_id: str, runs_root: Path, resume: Path | None = None, **kwargs: Any) -> Path:
        calls.append({"run_id": run_id, "resume": resume, **kwargs})
        directory = create_run_paths(run_id, runs_root).checkpoints
        steps = (100_000_000, 150_000_000, 200_000_000) if resume is None else (250_000_000,)
        for step in steps:
            _write_checkpoint(directory, config, "step", step)
        return directory / f"step-{steps[-1]:012d}.zip"

    def fake_evaluate_candidates(checkpoints, config, *, run_lineage, selection_seeds, final_seeds, episodes_per_seed, phase):
        return [
            EvaluationEvidence(
                checkpoint_inventory(checkpoint, config, run_lineage=run_lineage, phase=phase),
                "selection",
                tuple(selection_seeds),
                _episodes(tuple(selection_seeds), reward=500.0, velocity=0.9, fell=False),
                1.0,
                "test",
            )
            for checkpoint in checkpoints
        ]

    def fake_finalize(config_path, run_id, runs_root, overrides, **kwargs):
        return {"metrics_json": "report/metrics.json"}

    outcome: dict[str, Any] = {}
    try:
        outcome["result"] = run_g1_curriculum(
            flat_config_path=FLAT_CONFIG,
            rough_config_path=ROUGH_CONFIG,
            run_id="showcase-g1-transfer",
            runs_root=tmp_path,
            matrix_digest="d" * 64,
            image_digest="sha256:" + "e" * 64,
            gallery_example_id="g1-rough-terrain",
            selection_seeds=SELECTION_SEEDS,
            final_seeds=FINAL_SEEDS,
            selection_episodes_per_seed=2,
            final_episodes_per_seed=4,
            acceptance_criteria=ACCEPTANCE_CRITERIA,
            train_phase=fake_train_phase,
            evaluate_candidates_fn=fake_evaluate_candidates,
            finalize_fn=fake_finalize,
        )
    except Exception as exc:  # noqa: BLE001 - reported below if the resume never happened
        outcome["error"] = f"{type(exc).__name__}: {exc}"

    rough = [c for c in calls if c["resume"] is not None]
    assert rough, f"the rough phase never resumed; outcome={outcome}"
    assert rough[0]["allowed_source_environment"] == "G1JoystickFlatTerrain"
