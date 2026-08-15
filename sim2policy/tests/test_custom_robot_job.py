from __future__ import annotations

import json
import math
import time
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from sim2policy.custom_robot_contract import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    SCHEMA_VERSION,
    TASK_SUCCESS_RATE_THRESHOLD,
    TRAINING_PROFILE,
    canonical_json,
    preparation_fingerprint,
    sha256_bytes,
)
from sim2policy.custom_robot_io import validate_documents
from sim2policy.custom_robot_job import (
    PhaseTimeout,
    Publisher,
    _evaluate_policy,
    bounded_phase,
    build_policy_bundle,
    checkpoint_rank,
    inspect_policy_bundle,
    main,
    run_preparation,
    run_training,
)

ROOT = Path(__file__).resolve().parents[2]


class _ScriptedEnv:
    """Minimal environment that succeeds or fails on command.

    ``_evaluate_policy`` only reads the horizon, the per-step ``task_metrics``, and the
    termination flags, so scripting those is enough to drive the aggregate rule without
    paying for physics.
    """

    contract = {"episode_steps": 3}
    _outcomes: list[bool] = []
    _index = 0

    def __init__(self, *args, **kwargs) -> None:
        self.success = type(self)._outcomes[type(self)._index % len(type(self)._outcomes)]
        type(self)._index += 1

    def reset(self, seed=None):
        return None, {}

    def step(self, action):
        metrics = {"success": self.success, "fallen": not self.success}
        return None, 1.0, False, False, {"task_metrics": metrics}

    def close(self) -> None:
        return None


class _StubModel:
    def predict(self, observation, deterministic=True):
        return None, None


def _documents(
    *, robot_name: str = "sample-biped.xml", task: str = "stand-balance"
):
    robot = (ROOT / "saas" / "samples" / "robots" / robot_name).read_bytes()
    setup = canonical_json(
        {
            "objects": [],
            "robot_type": "quadruped" if "quadruped" in robot_name else "biped",
            "scene_preset_id": "flat-arena",
            "schema_version": SCHEMA_VERSION,
            "task_template_id": task,
        }
    )
    runtime = "registry.example/sim2policy@sha256:" + "a" * 64
    manifest = canonical_json(
        {
            "adapter_version": ADAPTER_VERSION,
            "fingerprint": preparation_fingerprint(
                robot_digest=sha256_bytes(robot),
                setup_digest=sha256_bytes(setup),
                runtime_image_digest=runtime,
            ),
            "preparation_id": "prepare-job-test",
            "preparation_profile_version": PREPARATION_PROFILE_VERSION,
            "reward_version": REWARD_VERSION,
            "robot": {
                "id": "robot-one",
                "path": "robot.xml",
                "sha256": sha256_bytes(robot),
                "size_bytes": len(robot),
                "source_digest": sha256_bytes(robot),
            },
            "runtime": {"image_digest": runtime},
            "schema_version": SCHEMA_VERSION,
            "setup": {
                "id": "setup-one",
                "path": "normalized-setup.json",
                "sha256": sha256_bytes(setup),
                "size_bytes": len(setup),
                "source_digest": sha256_bytes(setup),
            },
        }
    )
    return validate_documents(manifest, robot, setup, source_prefix="local")


def test_bounded_preparation_runs_compile_rollout_render_checker_and_ppo(tmp_path: Path) -> None:
    profile = replace(
        PREPARATION_PROFILE,
        rollout_steps=2,
        rollout_seeds=(7,),
        smoke_learning_steps=64,
    )
    report = run_preparation(
        _documents(),
        Publisher("prepare-job-test", "preparation", tmp_path),
        profile=profile,
    )
    assert report["status"] == "accepted"
    assert report["compiled"]["process_peak_rss_mib"] > 0
    assert [phase["name"] for phase in report["phases"]] == [
        "compile",
        "rollouts",
        "render",
        "environment-checker",
        "ppo-smoke",
    ]
    assert all(phase["status"] == "passed" for phase in report["phases"])
    assert (tmp_path / "report" / "render-probe.png").stat().st_size > 0
    persisted = json.loads((tmp_path / "report" / "preparation.json").read_text())
    unsigned = dict(persisted)
    digest = unsigned.pop("report_sha256")
    assert digest == sha256_bytes(canonical_json(unsigned))


def test_preparation_failure_is_sanitized_and_retryable_report_is_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unsafe_failure(*_args, **_kwargs):
        raise RuntimeError("/tenant/private/robot.xml <mujoco> SECRET")

    monkeypatch.setattr("sim2policy.custom_robot_job._render_probe", unsafe_failure)
    profile = replace(PREPARATION_PROFILE, rollout_steps=1, rollout_seeds=(7,))
    report = run_preparation(
        _documents(),
        Publisher("prepare-job-test", "preparation", tmp_path),
        profile=profile,
    )
    assert report["status"] == "failed"
    assert report["failure_phase"] == "render"
    assert report["failure_reason"] == "runtime-gate-failed"
    assert "SECRET" not in json.dumps(report)
    assert "/tenant" not in json.dumps(report)


def test_phase_timeout_is_enforced() -> None:
    with pytest.raises(PhaseTimeout), bounded_phase(1):
        time.sleep(2)


def test_bundle_layout_checksums_and_traversal_are_validated(tmp_path: Path) -> None:
    output = tmp_path / "bundle.zip"
    manifest = build_policy_bundle(
        output,
        fingerprint="f" * 64,
        robot_xml=b"<mujoco/>",
        normalized_setup=b"{}",
        checkpoint=b"checkpoint",
        resolved_config=b"{}",
        versions=b"{}",
        evaluation=b"{}",
    )
    assert inspect_policy_bundle(output, expected_fingerprint="f" * 64) == manifest
    with pytest.raises(ValueError, match="provenance"):
        inspect_policy_bundle(output, expected_fingerprint="0" * 64)

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../outside", b"no")
    with pytest.raises(ValueError, match="unsafe"):
        inspect_policy_bundle(unsafe, expected_fingerprint="f" * 64)

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(output) as source, zipfile.ZipFile(tampered, "w") as target:
        for name in source.namelist():
            value = source.read(name)
            target.writestr(name, b"changed" if name == "README.md" else value)
    with pytest.raises(ValueError, match="digest"):
        inspect_policy_bundle(tampered, expected_fingerprint="f" * 64)


def test_reduced_training_publishes_complete_checksummed_simulator_bundle(
    tmp_path: Path,
) -> None:
    profile = replace(
        TRAINING_PROFILE,
        total_timesteps=64,
        n_envs=1,
        checkpoint_every_steps=32,
        evaluation_every_steps=32,
        evaluation_episodes=2,
        evaluation_seeds=(11, 23),
        ppo_n_steps=64,
        ppo_batch_size=32,
        ppo_n_epochs=1,
    )
    metrics = run_training(
        _documents(),
        Publisher("custom-run-test", "run", tmp_path),
        profile=profile,
    )

    assert metrics["training"]["timesteps"] == 64
    assert metrics["runtime_seconds"] > 0
    assert metrics["benchmark"]["hourly_rate"] == 0.3968
    assert metrics["benchmark"]["currency"] == "USD"
    assert metrics["benchmark"]["estimated_cost"] > 0
    assert metrics["benchmark"]["process_peak_rss_mib"] > 0
    assert len(metrics["training"]["progress_evaluations"]) == 2
    assert isinstance(metrics["aggregate"]["task_threshold_achieved"], bool)
    assert metrics["simulator_only"] is True
    assert (tmp_path / "checkpoints" / "step-000000032.zip").is_file()
    assert (tmp_path / "checkpoints" / "step-000000064.zip").is_file()
    progress = json.loads((tmp_path / "metadata" / "progress.json").read_text())
    assert progress["progress"]["timesteps"] == 64
    manifest = json.loads((tmp_path / "report" / "artifacts.json").read_text())
    assert set(manifest["artifacts"]) == set(manifest["checksums"])
    for logical_name, relative in manifest["artifacts"].items():
        data = (tmp_path / relative).read_bytes()
        assert manifest["checksums"][logical_name] == {
            "sha256": sha256_bytes(data),
            "size_bytes": len(data),
        }
    bundle = inspect_policy_bundle(
        tmp_path / manifest["artifacts"]["policy_bundle"],
        expected_fingerprint=_documents().fingerprint,
    )
    assert bundle["simulator_only"] is True
    assert "run_id" not in bundle
    with zipfile.ZipFile(tmp_path / manifest["artifacts"]["policy_bundle"]) as archive:
        bundled_setup = json.loads(archive.read("setup/normalized-setup.json"))
        bundled_config = json.loads(archive.read("config/resolved-config.json"))
    assert "robot_id" not in bundled_setup
    assert "id" not in bundled_config["robot"]
    assert "id" not in bundled_config["preparation"]


def test_recovery_training_saves_and_reloads_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_video(_model, _documents, output: Path, _normalize=None) -> dict[str, int]:
        output.write_bytes(b"bounded-recovery-video")
        return {"frames": 2, "size_bytes": output.stat().st_size}

    monkeypatch.setattr("sim2policy.custom_robot_job._render_video", fake_video)
    profile = replace(
        TRAINING_PROFILE,
        total_timesteps=64,
        n_envs=1,
        checkpoint_every_steps=32,
        evaluation_every_steps=32,
        progress_evaluation_episodes=1,
        progress_evaluation_seeds=(101,),
        evaluation_episodes=1,
        evaluation_seeds=(11,),
        ppo_n_steps=64,
        ppo_batch_size=32,
        ppo_n_epochs=1,
    )
    metrics = run_training(
        _documents(
            robot_name="sample-quadruped.xml",
            task="recover-from-fall",
        ),
        Publisher("recovery-run-test", "run", tmp_path),
        profile=profile,
    )
    assert metrics["training"]["timesteps"] == 64
    assert (tmp_path / "checkpoints" / "final.zip").is_file()
    assert (tmp_path / "videos" / "final.mp4").read_bytes() == b"bounded-recovery-video"
    resolved = json.loads((tmp_path / "report" / "resolved-config.json").read_text())
    assert resolved["setup"]["task_template_id"] == "recover-from-fall"


def test_entrypoint_sanitizes_input_failure_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unsafe_load(*_args, **_kwargs):
        raise RuntimeError("/tenant/private/robot.xml SECRET")

    monkeypatch.setattr("sim2policy.custom_robot_job._load", unsafe_load)
    monkeypatch.setattr(
        "sys.argv",
        ["sim2policy-custom-robot", "prepare", "--identity", "prepare-one"],
    )
    assert main() == 2
    stderr = capsys.readouterr().err
    assert stderr == "custom robot prepare failed: runtime-gate-failed\n"


@pytest.mark.parametrize(
    ("successes", "expected"),
    [
        # The measured Nebius case: nineteen near-identical episodes and one seed that
        # tipped. Under the old `all()` rule this reported failure for a 95% policy.
        (19, True),
        (20, True),
        (18, True),
        # 0.85 is below the stated bar, so a genuinely unreliable policy still fails.
        (17, False),
        (10, False),
        (0, False),
    ],
)
def test_task_threshold_is_a_rate_against_a_stated_bar(
    monkeypatch: pytest.MonkeyPatch, successes: int, expected: bool
) -> None:
    outcomes = [True] * successes + [False] * (20 - successes)
    _ScriptedEnv._outcomes = outcomes
    _ScriptedEnv._index = 0
    monkeypatch.setattr("sim2policy.custom_robot_job.CustomRobotEnv", _ScriptedEnv)

    profile = replace(TRAINING_PROFILE, evaluation_episodes=20)
    evaluation = _evaluate_policy(_StubModel(), _documents(), profile)
    aggregate = evaluation["aggregate"]

    assert aggregate["success_rate"] == pytest.approx(successes / 20)
    assert aggregate["task_threshold_achieved"] is expected
    # The bar travels with the metrics so a reader can see what was applied.
    assert aggregate["task_success_rate_threshold"] == TASK_SUCCESS_RATE_THRESHOLD


@pytest.mark.parametrize(
    ("curve", "expected_timesteps", "why"),
    [
        # The measured local biped walk-forward run: success 0.000 at most checkpoints
        # with reward climbing the whole way, then 1.000 at the last.  Ranking by reward
        # alone would pick 2_750_000 -- a crouch that scores zero on the gate -- and only
        # the near-tie at 3_000_000 saved it.
        (
            [
                (2_000_000, 0.75, 2418.0),
                (2_500_000, 0.0, 2878.8),
                (2_750_000, 0.0, 3184.9),
                (3_000_000, 1.0, 3542.7),
            ],
            3_000_000,
            "highest success rate wins even when a later reward is close",
        ),
        # Reward still breaks ties, so an equally successful but better-performing
        # checkpoint is preferred.
        (
            [(1_000_000, 1.0, 900.0), (2_000_000, 1.0, 3300.0), (3_000_000, 1.0, 3100.0)],
            2_000_000,
            "reward breaks ties among equally successful checkpoints",
        ),
        # A run that never succeeds still publishes its best-rewarded checkpoint rather
        # than nothing.
        (
            [(1_000_000, 0.0, 500.0), (2_000_000, 0.0, 2600.0), (3_000_000, 0.0, 1200.0)],
            2_000_000,
            "falls back to reward when nothing succeeds",
        ),
    ],
)
def test_published_checkpoint_is_ranked_by_success_then_reward(
    curve: list[tuple[int, float, float]], expected_timesteps: int, why: str
) -> None:
    """The selector must optimise the quantity the gate measures.

    Before the walk-forward posture floor, success and reward moved together and ranking
    by reward was a fair proxy.  The floor decoupled them: a crouching policy is alive,
    fast and on the line, so it out-earns an upright one while scoring zero.
    """
    best_rank = (-math.inf, -math.inf)
    best_timesteps = 0
    for timesteps, success_rate, mean_reward in curve:
        rank = checkpoint_rank({"success_rate": success_rate, "mean_reward": mean_reward})
        if rank > best_rank:
            best_rank, best_timesteps = rank, timesteps
    assert best_timesteps == expected_timesteps, why
