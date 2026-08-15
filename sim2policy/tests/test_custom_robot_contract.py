from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from sim2policy.custom_robot_contract import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    SCHEMA_VERSION,
    TASK_CONTRACTS,
    TASK_ROBOT_TYPES,
    TRAINING_PROFILE,
    TRAINING_PROFILE_VERSION,
    contract_summary,
    evaluation_seeds,
    load_json_schema,
    preparation_fingerprint,
    profile_payloads,
    target_height_scale,
    validate_safe_id,
)

FIXTURES = Path(__file__).parent / "fixtures" / "custom_robot"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "name,expected_id",
    [
        ("normalized-setup.schema.json", "sim2policy/custom-robot/normalized-setup/v2"),
        (
            "preparation-input-manifest.schema.json",
            "sim2policy/custom-robot/preparation-input-manifest/v2",
        ),
        ("preparation-report.schema.json", "sim2policy/custom-robot/preparation-report/v2"),
        ("resolved-custom-job.schema.json", "sim2policy/custom-robot/resolved-job/v2"),
        (
            "policy-bundle-manifest.schema.json",
            "sim2policy/custom-robot/policy-bundle-manifest/v2",
        ),
        (
            "preparation-api-state.schema.json",
            "sim2policy/custom-robot/preparation-api-state/v2",
        ),
        (
            "custom-artifact-manifest.schema.json",
            "sim2policy/custom-robot/artifact-manifest/v2",
        ),
    ],
)
def test_versioned_json_schemas_are_packaged(name: str, expected_id: str) -> None:
    schema = load_json_schema(name)
    assert schema["$id"] == expected_id
    assert schema["additionalProperties"] is False


def test_golden_fingerprint_is_stable() -> None:
    manifest = _fixture("preparation-input-manifest.json")
    assert (
        preparation_fingerprint(
            robot_digest="1" * 64,
            setup_digest="2" * 64,
            runtime_image_digest="registry.example/sim2policy:sb3-abcdef123456",
        )
        == manifest["fingerprint"]
    )


def test_golden_documents_carry_matching_contract_versions() -> None:
    manifest = _fixture("preparation-input-manifest.json")
    resolved = _fixture("resolved-custom-job.json")
    report = _fixture("preparation-report.json")
    bundle = _fixture("policy-bundle-manifest.json")
    assert manifest["schema_version"] == resolved["schema_version"] == SCHEMA_VERSION
    assert bundle["schema_version"] == report["schema_version"] == SCHEMA_VERSION
    assert manifest["adapter_version"] == ADAPTER_VERSION
    assert manifest["reward_version"] == REWARD_VERSION
    assert manifest["preparation_profile_version"] == PREPARATION_PROFILE_VERSION
    assert resolved["training"]["profile_version"] == TRAINING_PROFILE_VERSION  # type: ignore[index]
    expected_training = {
        "profile": "custom-ppo-quick",
        "profile_version": TRAINING_PROFILE_VERSION,
        **profile_payloads()["training"],
    }
    assert resolved["training"] == expected_training
    assert bundle["simulator_only"] is True


def test_all_versioned_schemas_have_golden_documents() -> None:
    schema_names = {
        path.name.removesuffix(".schema.json")
        for path in (FIXTURES.parents[2] / "src" / "sim2policy" / "schemas" / "custom_robot").glob(
            "*.schema.json"
        )
    }
    fixture_names = {path.stem for path in FIXTURES.glob("*.json")}
    assert schema_names == fixture_names


@pytest.mark.parametrize(
    "document",
    [
        "normalized-setup",
        "preparation-input-manifest",
        "preparation-report",
        "preparation-api-state",
        "resolved-custom-job",
        "custom-artifact-manifest",
        "policy-bundle-manifest",
    ],
)
def test_golden_document_validates_against_its_schema(document: str) -> None:
    schema = load_json_schema(f"{document}.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_fixture(f"{document}.json"))


def test_profiles_are_fixed_and_bounded() -> None:
    assert (PREPARATION_PROFILE.platform, PREPARATION_PROFILE.preset) == (
        "cpu-d3",
        "4vcpu-16gb",
    )
    assert (TRAINING_PROFILE.platform, TRAINING_PROFILE.preset) == (
        "cpu-d3",
        "16vcpu-64gb",
    )
    assert PREPARATION_PROFILE.timeout_seconds <= 600
    assert TRAINING_PROFILE.total_timesteps == 3_000_000
    assert TRAINING_PROFILE.n_envs == 16
    # One vector environment per provisioned vCPU, and a budget the timeout can hold at
    # the throughput measured for the v1 profile (~1.4k steps/s on half the cores).
    assert TRAINING_PROFILE.n_envs <= TRAINING_PROFILE.cpu_count
    assert TRAINING_PROFILE.timeout_seconds <= 10_800
    assert TRAINING_PROFILE.normalize_observations is True
    assert TRAINING_PROFILE.publish_best_checkpoint is True


def test_evaluation_scores_as_many_distinct_seeds_as_it_reports_episodes() -> None:
    """Twenty reported episodes must be twenty different initial conditions.

    The previous rule collided at the shipped profile — base 37 at index 2 and base 23 at
    index 16 both produced seed 39 — so one initial condition was scored twice and the
    gate was computed over nineteen.  A measured biped run failed on that seed and lost
    two of twenty rather than one of nineteen.
    """
    for seeds, episodes in (
        (TRAINING_PROFILE.evaluation_seeds, TRAINING_PROFILE.evaluation_episodes),
        (
            TRAINING_PROFILE.progress_evaluation_seeds,
            TRAINING_PROFILE.progress_evaluation_episodes,
        ),
    ):
        drawn = evaluation_seeds(seeds, episodes)
        assert len(drawn) == episodes
        assert len(set(drawn)) == episodes, drawn
        # Deterministic, and the first family is still the declared base seeds.
        assert drawn == evaluation_seeds(seeds, episodes)
        assert drawn[: len(seeds)] == tuple(seeds)[: len(drawn)]

    # Far more episodes than base seeds still cannot collide.
    many = evaluation_seeds((11, 23, 37, 53, 71), 500)
    assert len(set(many)) == 500
    with pytest.raises(ValueError, match="distinct"):
        evaluation_seeds((7, 7), 4)
    with pytest.raises(ValueError, match="stride"):
        evaluation_seeds((7, 5000), 4)


def test_every_task_states_a_height_target_for_every_robot_type_it_accepts() -> None:
    """A morphology added without a measured target must fail here, not in training.

    ``target_height_scale`` is per robot type for the locomotion tasks because the
    quadruped walks at 0.54 of its spawn height and the biped at 0.88; falling back to
    another morphology's number produces a target the robot cannot reach, and the height
    reward's Gaussian is narrow enough that an unreachable target reads as no gradient
    at all rather than as a hard task.
    """
    for task, robot_types in TASK_ROBOT_TYPES.items():
        for robot_type in robot_types:
            scale = target_height_scale(task, robot_type)
            assert 0.0 < scale <= 1.0, (task, robot_type, scale)
    with pytest.raises(KeyError, match="no target_height_scale"):
        target_height_scale("walk-forward", "hexapod")


def test_standing_tasks_bound_ground_contact_as_well_as_height() -> None:
    """Posture has to be stated, not inferred from a height.

    Height was the only posture signal through v16, and it cannot separate standing from
    kneeling for a robot whose legs fold beneath it: the quadruped's knees sit 0.28 m
    below its torso and the target was 0.339 m, so the shipped policy met it on its
    knees and every metric agreed.  Both locomotion tasks must therefore bound what is
    touching the ground.  ``recover-from-fall`` is excluded on purpose — it resets the
    robot onto its side, so non-foot contact there is the task, not a failure.
    """
    for task in ("stand-balance", "walk-forward"):
        contract = TASK_CONTRACTS[task]
        assert 0.0 < float(contract["success_max_unsupported_contact"]) < 0.5, task
        assert float(contract["weights"]["ground_contact"]) < 0.0, task
    recovery = TASK_CONTRACTS["recover-from-fall"]
    assert "success_max_unsupported_contact" not in recovery
    assert float(recovery["weights"]["ground_contact"]) == 0.0


def test_contract_summary_contains_complete_builder_matrix() -> None:
    summary = contract_summary()
    assert summary["supported_robot_types"] == ["biped", "quadruped"]
    assert summary["supported_tasks"] == [
        "stand-balance", "walk-forward", "recover-from-fall"
    ]
    assert summary["supported_scenes"] == [
        "flat-arena", "ramp-course", "hurdle-course", "step-course"
    ]
    assert set(summary["object_contracts"]) == {"box", "ramp", "hurdle", "step"}
    assert summary["max_objects"] == 6


def test_unsafe_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_id("../tenant-prefix")
