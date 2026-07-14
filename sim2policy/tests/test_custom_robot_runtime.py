from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sim2policy.custom_robot_contract import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    SCHEMA_VERSION,
    canonical_json,
    preparation_fingerprint,
    sha256_bytes,
)
from sim2policy.custom_robot_env import (
    CustomRobotCompatibilityError,
    CustomRobotEnv,
    compose_server_mjcf,
    make_vectorized_env,
)
from sim2policy.custom_robot_io import (
    CustomInputError,
    input_prefix,
    load_inputs_from_s3,
    validate_documents,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "saas" / "samples" / "robots"


def _robot(name: str = "sample-biped.xml") -> bytes:
    return (SAMPLES / name).read_bytes()


def _documents(
    *,
    robot_name: str = "sample-biped.xml",
    task: str = "stand-balance",
    scene: str = "flat-arena",
) -> tuple[bytes, bytes, bytes]:
    robot = _robot(robot_name)
    robot_id = "robot-one"
    setup = canonical_json(
        {
            "objects": [],
            "robot_type": "quadruped" if "quadruped" in robot_name else "biped",
            "scene_preset_id": scene,
            "schema_version": SCHEMA_VERSION,
            "task_template_id": task,
        }
    )
    robot_source = sha256_bytes(robot)
    setup_source = sha256_bytes(setup)
    runtime = "registry.example/sim2policy@sha256:" + "a" * 64
    manifest = canonical_json(
        {
            "adapter_version": ADAPTER_VERSION,
            "fingerprint": preparation_fingerprint(
                robot_digest=robot_source,
                setup_digest=setup_source,
                runtime_image_digest=runtime,
            ),
            "preparation_id": "prepare-one",
            "preparation_profile_version": PREPARATION_PROFILE_VERSION,
            "reward_version": REWARD_VERSION,
            "robot": {
                "id": robot_id,
                "path": "robot.xml",
                "sha256": sha256_bytes(robot),
                "size_bytes": len(robot),
                "source_digest": robot_source,
            },
            "runtime": {"image_digest": runtime},
            "schema_version": SCHEMA_VERSION,
            "setup": {
                "id": "setup-one",
                "path": "normalized-setup.json",
                "sha256": sha256_bytes(setup),
                "size_bytes": len(setup),
                "source_digest": setup_source,
            },
        }
    )
    return manifest, robot, setup


@pytest.mark.parametrize("robot_name", ["sample-biped.xml", "sample-quadruped.xml"])
@pytest.mark.parametrize("task", ["stand-balance", "walk-forward"])
@pytest.mark.parametrize("scene", ["flat-arena", "ramp-course"])
def test_canonical_matrix_compiles_and_steps(robot_name: str, task: str, scene: str) -> None:
    env = CustomRobotEnv(
        _robot(robot_name).decode(),
        {"task_template_id": task, "scene_preset_id": scene, "objects": []},
    )
    first, _ = env.reset(seed=19)
    second, _ = env.reset(seed=19)
    assert np.array_equal(first, second)
    observation, reward, terminated, truncated, info = env.step(
        np.zeros(env.action_space.shape, dtype=np.float32)
    )
    assert env.observation_space.contains(observation)
    assert np.isfinite(reward)
    assert not terminated
    assert not truncated
    assert set(info["task_metrics"]) >= {
        "fallen",
        "forward_progress",
        "forward_velocity",
        "success",
    }
    assert env.schemas.observation_sha256 == env._build_schemas().observation_sha256
    assert env.schemas.action_sha256 == env._build_schemas().action_sha256
    env.close()


def test_server_owns_world_settings_and_action_mapping() -> None:
    xml = (
        _robot()
        .decode()
        .replace(
            '<option timestep="0.004" gravity="0 0 -9.81"/>',
            '<option timestep="0.5" gravity="0 0 99"/>',
        )
    )
    setup = {"task_template_id": "stand-balance", "scene_preset_id": "ramp-course", "objects": []}
    composed = compose_server_mjcf(xml, setup)
    assert 'gravity="0 0 -9.81"' in composed
    assert 'timestep="0.004"' in composed
    assert "99" not in composed
    assert 'name="server_floor"' in composed
    assert 'name="server_ramp"' in composed
    env = CustomRobotEnv(xml, setup)
    np.testing.assert_allclose(env._map_action(np.full(env.model.nu, -2)), env.ctrl_ranges[:, 0])
    np.testing.assert_allclose(env._map_action(np.full(env.model.nu, 2)), env.ctrl_ranges[:, 1])
    env.close()


def test_vector_factory_uses_seeded_generic_environments() -> None:
    vector = make_vectorized_env(
        _robot().decode(),
        {"task_template_id": "walk-forward", "scene_preset_id": "flat-arena", "objects": []},
        seed=7,
        n_envs=2,
    )
    observation = vector.reset()
    assert observation.shape[0] == 2
    vector.close()


@pytest.mark.parametrize(
    "addition,reason",
    [
        ("<sensor><accelerometer name='x' site='x'/></sensor>", "top-level-feature-not-supported"),
        ("<worldbody><geom type='plane'/></worldbody>", "geometry-type-not-supported"),
        ("<worldbody/>", "multiple-worldbody-sections"),
    ],
)
def test_rejects_unsupported_tenant_world_features(addition: str, reason: str) -> None:
    xml = _robot().decode().replace("</mujoco>", f"{addition}</mujoco>")
    with pytest.raises(CustomRobotCompatibilityError, match=reason):
        compose_server_mjcf(
            xml,
            {"task_template_id": "stand-balance", "scene_preset_id": "flat-arena", "objects": []},
        )


def test_non_finite_action_fails_closed() -> None:
    env = CustomRobotEnv(
        _robot().decode(),
        {"task_template_id": "stand-balance", "scene_preset_id": "flat-arena", "objects": []},
    )
    env.reset(seed=7)
    with pytest.raises(CustomRobotCompatibilityError, match="action-non-finite"):
        env.step(np.full(env.model.nu, np.nan, dtype=np.float32))
    env.close()


def test_runaway_state_terminates_with_stable_reason() -> None:
    env = CustomRobotEnv(
        _robot().decode(),
        {"task_template_id": "stand-balance", "scene_preset_id": "flat-arena", "objects": []},
    )
    env.reset(seed=7)
    env.data.qvel[env.root_dof_adr] = 251.0
    _, _, terminated, _, info = env.step(np.zeros(env.model.nu, dtype=np.float32))
    assert terminated is True
    assert info["task_metrics"]["runaway"] is True
    assert info["termination_reason"] == "runaway"
    env.close()


@pytest.mark.parametrize(
    "transform,reason",
    [
        (
            lambda xml: xml.replace('ctrlrange="-1 1"', 'ctrlrange="-100000 100000"'),
            "actuator-control-range-invalid",
        ),
        (
            lambda xml: xml.replace(
                '<geom name="pelvis_geom"',
                '<geom mass="100000" name="pelvis_geom"',
                1,
            ),
            "compiled-mass-inertia-invalid",
        ),
        (
            lambda xml: xml.replace(
                '<motor name="left_hip_motor"', '<position name="left_hip_motor"'
            ),
            "motor-actuators-required",
        ),
    ],
)
def test_compiled_training_bounds_reject_extreme_or_unsupported_models(
    transform, reason: str
) -> None:
    with pytest.raises(CustomRobotCompatibilityError, match=reason):
        CustomRobotEnv(
            transform(_robot().decode()),
            {
                "task_template_id": "stand-balance",
                "scene_preset_id": "flat-arena",
                "objects": [],
            },
        )


def test_manifest_loader_verifies_exact_inputs_and_rejects_tampering() -> None:
    manifest, robot, setup = _documents()
    loaded = validate_documents(manifest, robot, setup, source_prefix="safe")
    assert loaded.setup["objects"] == []
    with pytest.raises(CustomInputError, match="digest"):
        validate_documents(manifest, b"X" + robot[1:], setup, source_prefix="safe")


class _Body:
    def __init__(self, value: bytes) -> None:
        self._value = value

    def read(self, maximum: int) -> bytes:
        return self._value[:maximum]


class _S3:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.keys: list[str] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "bucket"
        self.keys.append(Key)
        value = self.objects[Key]
        return {"Body": _Body(value), "ContentLength": len(value)}


def test_s3_loader_derives_prefix_only_from_opaque_identity() -> None:
    manifest, robot, setup = _documents()
    prefix = input_prefix("prepare-one", "preparation")
    client = _S3(
        {
            f"{prefix}/input-manifest.json": manifest,
            f"{prefix}/robot.xml": robot,
            f"{prefix}/normalized-setup.json": setup,
        }
    )
    load_inputs_from_s3("prepare-one", kind="preparation", client=client, bucket="bucket")
    assert client.keys == [
        f"{prefix}/input-manifest.json",
        f"{prefix}/robot.xml",
        f"{prefix}/normalized-setup.json",
    ]
    with pytest.raises(ValueError, match="unsafe"):
        input_prefix("../tenant", "preparation")
