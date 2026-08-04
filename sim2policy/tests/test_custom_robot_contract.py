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
    TRAINING_PROFILE,
    TRAINING_PROFILE_VERSION,
    contract_summary,
    load_json_schema,
    preparation_fingerprint,
    profile_payloads,
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
