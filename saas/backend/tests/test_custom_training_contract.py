from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.custom_training import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE,
    REASON_FEATURE_DISABLED,
    REASON_NOT_PREPARED,
    REWARD_VERSION,
    TRAINING_PROFILE,
    build_input_documents,
    canonical_normalized_setup,
    eligibility,
    resolved_profile_payload,
)
from app.models import CatalogObject, RobotAsset, RobotSetup, ValidationSummary
from app.settings import CustomTrainingSettings, SettingsError


def _robot() -> RobotAsset:
    return RobotAsset(
        id="robot-fixture",
        name="Fixture",
        filename="fixture.xml",
        robot_type="quadruped",
        digest="1" * 64,
        validation=ValidationSummary(
            body_count=2,
            joint_count=2,
            actuator_count=1,
            geom_count=2,
            joint_names=["root", "hip"],
            actuator_names=["hip_motor"],
        ),
        validated_at="2026-07-14T00:00:00+00:00",
    )


def _setup(**updates: object) -> RobotSetup:
    data: dict[str, object] = {
        "id": "setup-fixture",
        "name": "Fixture setup",
        "robot_id": "robot-fixture",
        "robot_name": "Fixture",
        "robot_type": "quadruped",
        "task_template_id": "walk-forward",
        "scene_preset_id": "flat-arena",
        "objects": [],
        "digest": "2" * 64,
        "created_at": "2026-07-14T00:00:00+00:00",
    }
    data.update(updates)
    return RobotSetup.model_validate(data)


def test_every_catalog_valid_setup_is_eligible() -> None:
    assert eligibility(_setup()).reason == REASON_NOT_PREPARED
    assert eligibility(_setup(), enabled=False).reason == REASON_FEATURE_DISABLED
    assert eligibility(_setup(task_template_id="recover-from-fall")).eligible is True
    assert eligibility(
        _setup(robot_type="biped", task_template_id="recover-from-fall")
    ).eligible is False
    assert eligibility(_setup(scene_preset_id="step-course")).eligible is True
    custom = CatalogObject(
        object_type="box",
        x=1,
        y=0,
        z=0,
        yaw_degrees=0,
        width=1,
        depth=1,
        height=1,
        source="custom",
    )
    assert eligibility(_setup(objects=[custom])).reason == REASON_NOT_PREPARED


def test_ramp_preset_object_is_not_tenant_optional() -> None:
    preset = CatalogObject(
        object_type="ramp",
        x=3,
        y=0,
        z=0,
        yaw_degrees=0,
        width=1.5,
        depth=3,
        height=0.6,
        source="preset",
    )
    result = eligibility(_setup(scene_preset_id="ramp-course", objects=[preset]))
    assert result.eligible is True


def test_input_documents_are_canonical_and_fingerprinted() -> None:
    robot_xml = (
        Path(__file__).parents[2] / "samples/robots/sample-quadruped.xml"
    ).read_text(encoding="utf-8")
    robot_bytes, setup_bytes, manifest = build_input_documents(
        preparation_id="preparation-fixture",
        robot=_robot(),
        robot_xml=robot_xml,
        setup=_setup(),
        runtime_image_digest="registry.example/sim2policy:sb3-abcdef123456",
    )
    assert robot_bytes == robot_xml.encode()
    assert setup_bytes.endswith(b"}") and not setup_bytes.endswith(b"\n")
    assert (
        manifest["fingerprint"]
        == "7910984c15895ded12541fce56860cce217a7419c99102aebef1d32f17ed7ef0"
    )
    assert manifest["adapter_version"] == ADAPTER_VERSION
    assert manifest["reward_version"] == REWARD_VERSION
    assert manifest["setup"]["size_bytes"] == len(setup_bytes)


def test_fixed_profiles_are_cpu_only() -> None:
    assert (PREPARATION_PROFILE.platform, PREPARATION_PROFILE.preset) == (
        "cpu-d3",
        "4vcpu-16gb",
    )


def test_control_plane_matches_runtime_golden_contracts() -> None:
    fixtures = (
        Path(__file__).parents[3]
        / "sim2policy"
        / "tests"
        / "fixtures"
        / "custom_robot"
    )
    normalized = json.loads((fixtures / "normalized-setup.json").read_text())
    resolved = json.loads((fixtures / "resolved-custom-job.json").read_text())
    assert canonical_normalized_setup(_setup()) == normalized
    golden_training = dict(resolved["training"])
    golden_training.pop("profile")
    golden_training.pop("profile_version")
    assert resolved_profile_payload()["training"] == golden_training
    assert (TRAINING_PROFILE.platform, TRAINING_PROFILE.preset) == (
        "cpu-d3",
        "16vcpu-64gb",
    )


def test_custom_training_settings_are_disabled_by_default() -> None:
    settings = CustomTrainingSettings.from_env({}, orchestration_backend="mock")
    assert settings.enabled is False
    assert settings.runtime_image == "local-custom-robot-sb3-v1"


def test_enabled_nebius_requires_immutable_sb3_image() -> None:
    with pytest.raises(SettingsError, match="missing"):
        CustomTrainingSettings.from_env(
            {"CUSTOM_ROBOT_TRAINING_ENABLED": "true"}, orchestration_backend="nebius"
        )
    with pytest.raises(SettingsError, match="immutable"):
        CustomTrainingSettings.from_env(
            {
                "CUSTOM_ROBOT_TRAINING_ENABLED": "true",
                "CUSTOM_ROBOT_SB3_IMAGE": "registry/sim2policy:sb3-runtime",
            },
            orchestration_backend="nebius",
        )
    settings = CustomTrainingSettings.from_env(
        {
            "CUSTOM_ROBOT_TRAINING_ENABLED": "true",
            "CUSTOM_ROBOT_SB3_IMAGE": "registry/sim2policy:sb3-abcdef123456",
        },
        orchestration_backend="nebius",
    )
    assert settings.enabled is True


def test_quota_configuration_is_bounded() -> None:
    with pytest.raises(SettingsError, match="between"):
        CustomTrainingSettings.from_env(
            {"CUSTOM_ROBOT_MAX_ACTIVE_PREPARATIONS": "0"},
            orchestration_backend="mock",
        )
