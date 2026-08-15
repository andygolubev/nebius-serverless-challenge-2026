from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np
import pytest

from sim2policy.custom_robot_contract import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    SCENE_CONTRACTS,
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


def _setup(task: str, scene: str = "flat-arena", robot_name: str = "sample-biped.xml", **extra):
    """A setup document of the shape ``validate_setup`` accepts.

    ``robot_type`` is part of that shape and the runtime reads it — the height target is
    stated per morphology — so tests that build a setup inline have to carry it too.
    """
    return {
        "robot_type": "quadruped" if "quadruped" in robot_name else "biped",
        "task_template_id": task,
        "scene_preset_id": scene,
        "objects": [],
        **extra,
    }


def _documents(
    *,
    robot_name: str = "sample-biped.xml",
    task: str = "stand-balance",
    scene: str = "flat-arena",
    objects: list[dict[str, object]] | None = None,
) -> tuple[bytes, bytes, bytes]:
    robot = _robot(robot_name)
    robot_id = "robot-one"
    setup = canonical_json(
        {
            "objects": objects or [],
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
        _setup(task, scene, robot_name),
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
    setup = _setup(
        "stand-balance",
        "ramp-course",
        objects=SCENE_CONTRACTS["ramp-course"]["preset_objects"],
    )
    composed = compose_server_mjcf(xml, setup)
    assert 'gravity="0 0 -9.81"' in composed
    assert 'timestep="0.004"' in composed
    assert 'gravity="0 0 99"' not in composed
    assert 'name="server_floor"' in composed
    assert 'name="server_object_0_ramp"' in composed
    env = CustomRobotEnv(xml, setup)
    np.testing.assert_allclose(env._map_action(np.full(env.model.nu, -2)), env.ctrl_ranges[:, 0])
    np.testing.assert_allclose(env._map_action(np.full(env.model.nu, 2)), env.ctrl_ranges[:, 1])
    env.close()


@pytest.mark.parametrize("scene", ["hurdle-course", "step-course"])
def test_server_composes_every_preset_terrain(scene: str) -> None:
    setup = _setup("walk-forward", scene, objects=SCENE_CONTRACTS[scene]["preset_objects"])
    composed = compose_server_mjcf(_robot().decode(), setup)
    assert composed.count("server_object_") == 3
    env = CustomRobotEnv(_robot().decode(), setup)
    observation, _ = env.reset(seed=7)
    assert env.observation_space.contains(observation)
    env.close()


def test_custom_primitives_compose_and_recovery_reset_is_bounded(monkeypatch) -> None:
    objects = [
        {"object_type": kind, "x": 2.0 + index, "y": 0.0, "z": 0.0,
         "yaw_degrees": 15.0, "width": width, "depth": depth,
         "height": height, "source": "custom"}
        for index, (kind, width, depth, height) in enumerate(
            (("box", 1.0, 1.0, 0.3), ("ramp", 1.5, 3.0, 0.6),
             ("hurdle", 2.0, 0.15, 0.35), ("step", 2.0, 1.0, 0.2))
        )
    ]
    setup = _setup(
        "recover-from-fall", robot_name="sample-quadruped.xml", objects=objects
    )
    composed = compose_server_mjcf(_robot("sample-quadruped.xml").decode(), setup)
    assert all(
        f"server_object_{index}_{item['object_type']}" in composed
        for index, item in enumerate(objects)
    )
    env = CustomRobotEnv(_robot("sample-quadruped.xml").decode(), setup, render_mode="rgb_array")
    observation, _ = env.reset(seed=19)
    _, upright, _, _ = env._root_features()
    assert env.observation_space.contains(observation)
    assert abs(upright) < 0.4
    assert env.data.qpos[env.root_qpos_adr + 2] >= 0.12
    _, reward, terminated, _, info = env.step(np.zeros(env.model.nu, dtype=np.float32))
    assert np.isfinite(reward)
    assert terminated is False
    assert info["termination_reason"] is None
    class FakeRenderer:
        def __init__(self, _model, *, height: int, width: int) -> None:
            self.shape = (height, width, 3)

        def update_scene(self, _data, *, camera) -> None:
            # The video camera tracks the robot's root body rather than watching the
            # fixed ``server_camera`` viewpoint, which a walking policy simply left.
            assert camera.type == mujoco.mjtCamera.mjCAMERA_TRACKING
            assert camera.trackbodyid == env.root_body_id

        def render(self):
            return np.zeros(self.shape, dtype=np.uint8)

        def close(self) -> None:
            pass

    monkeypatch.setattr("sim2policy.custom_robot_env.mujoco.Renderer", FakeRenderer)
    assert env.render().shape == (480, 640, 3)
    env.close()


def test_vector_factory_uses_seeded_generic_environments() -> None:
    vector = make_vectorized_env(
        _robot().decode(),
        _setup("walk-forward"),
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
            _setup("stand-balance"),
        )


def test_non_finite_action_fails_closed() -> None:
    env = CustomRobotEnv(
        _robot().decode(),
        _setup("stand-balance"),
    )
    env.reset(seed=7)
    with pytest.raises(CustomRobotCompatibilityError, match="action-non-finite"):
        env.step(np.full(env.model.nu, np.nan, dtype=np.float32))
    env.close()


def test_runaway_state_terminates_with_stable_reason() -> None:
    env = CustomRobotEnv(
        _robot().decode(),
        _setup("stand-balance"),
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


def test_normalized_primitive_contract_rejects_tampering_before_compilation() -> None:
    valid = {
        "object_type": "hurdle", "x": 2.0, "y": 0.0, "z": 0.0,
        "yaw_degrees": 0.0, "width": 2.0, "depth": 0.15,
        "height": 0.35, "source": "custom",
    }
    manifest, robot, setup = _documents(objects=[valid])
    normalized = validate_documents(manifest, robot, setup, source_prefix="safe")
    assert normalized.setup["objects"] == [valid]
    for bad in (
        {**valid, "height": 1.6},
        {**valid, "source": "uploaded"},
        {**valid, "script": "unsafe"},
    ):
        bad_manifest, bad_robot, bad_setup = _documents(objects=[bad])
        with pytest.raises(CustomInputError, match="normalized setup object"):
            validate_documents(bad_manifest, bad_robot, bad_setup, source_prefix="safe")
    incompatible_manifest, incompatible_robot, incompatible_setup = _documents(
        robot_name="sample-biped.xml", task="recover-from-fall"
    )
    with pytest.raises(CustomInputError, match="incompatible"):
        validate_documents(
            incompatible_manifest,
            incompatible_robot,
            incompatible_setup,
            source_prefix="safe",
        )


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


@pytest.mark.parametrize(
    ("robot_name", "height_fraction", "expected", "why"),
    [
        # Fractions are of ``reference_height``, so these are the numbers the measured
        # runs reported.  The bar is 0.8 of the task's target, which differs by
        # morphology -- 0.44 of reference for the quadruped, 0.72 for the biped -- which
        # is what the two 0.50 rows below are for.
        #
        # The biped crouch that prompted this check: it crossed the arena at 58% of its
        # standing height, folded onto one knee, and scored 20/20 under the old
        # criterion.
        ("sample-biped.xml", 0.58, False, "the crouch that was certified as a gait"),
        ("sample-biped.xml", 0.50, False, "clears the quadruped's bar, not the biped's"),
        ("sample-biped.xml", 0.82, True, "the upright gait, at 0.91 of target"),
        ("sample-quadruped.xml", 0.50, True, "a normal quadruped gait, at 0.29 m"),
        ("sample-quadruped.xml", 0.35, False, "dragging along at 0.21 m"),
    ],
)
def test_walk_forward_success_requires_a_standing_posture(
    monkeypatch: pytest.MonkeyPatch,
    robot_name: str,
    height_fraction: float,
    expected: bool,
    why: str,
) -> None:
    """A rollout that travels folded down is not walking, however fast it goes.

    Velocity and drift are both satisfied here; only the height differs, so this fails if
    the height term is ever dropped from the criterion.

    Note what this bar does *not* catch, which
    ``test_height_floor_alone_cannot_reject_a_kneeling_quadruped`` pins directly: a
    quadruped kneels at very nearly the height it walks at, so no floor stated in metres
    separates the two for that morphology.  ``success_max_unsupported_contact`` is what
    does.
    """
    env = CustomRobotEnv(
        _robot(robot_name).decode(), _setup("walk-forward", robot_name=robot_name)
    )
    env.reset(seed=11)
    env.steps = int(env.contract["episode_steps"])
    # A read-only property on the class, so it is patched there rather than per instance.
    monkeypatch.setattr(CustomRobotEnv, "mean_forward_velocity", property(lambda _: 0.8))
    try:
        assert (
            env._success(
                upright=0.99,
                height=env.reference_height * height_fraction,
                lateral_drift=0.05,
                fallen=False,
                unsupported_contact_rate=0.0,
                mean_stance_offset=0.0,
            )
            is expected
        ), why
    finally:
        env.close()


def test_height_floor_alone_cannot_reject_a_kneeling_quadruped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason ``ground_contact`` exists, stated as an assertion rather than a comment.

    Stated against the *target* rather than against the 0.314 m the v16 policy knelt at.
    That literal number stopped being the interesting case in v21, which raised the
    quadruped's walking target to 0.75 of reference and so happens to put the floor above
    it -- but that is an accident of one number, not height becoming able to describe a
    posture.  A robot can kneel at any height its thighs will hold it at, including
    exactly the one being asked for, and this pins that: at the height the reward wants,
    with velocity and drift satisfied, the only thing left that can tell kneeling from
    standing is what is carrying the weight.
    """
    env = CustomRobotEnv(
        _robot("sample-quadruped.xml").decode(),
        _setup("walk-forward", robot_name="sample-quadruped.xml"),
    )
    try:
        env.reset(seed=11)
        env.steps = int(env.contract["episode_steps"])
        # A kneeling quadruped travels: the measured v16 policy dragged itself across the
        # arena at 0.80 m/s, which is why every other criterion here is satisfied.
        monkeypatch.setattr(CustomRobotEnv, "mean_forward_velocity", property(lambda _: 0.8))
        # A kneel that meets the ask exactly, which is the pose no height floor can ever
        # reject: the floor is a fraction of this number.
        kneeling = env.reference_height * env.target_height_scale
        floor = kneeling * float(env.contract["success_min_height_of_target"])
        assert kneeling > floor, "the floor is a fraction of the target, so this cannot invert"
        assert env._success(
            upright=0.99, height=kneeling, lateral_drift=0.05, fallen=False,
            unsupported_contact_rate=0.0,
            mean_stance_offset=0.0,
        ), "height and velocity alone certify the kneel"
        assert not env._success(
            upright=0.99, height=kneeling, lateral_drift=0.05, fallen=False,
            unsupported_contact_rate=0.6,
            mean_stance_offset=0.0,
        ), "what it was standing on is the only thing that rejects it"
    finally:
        env.close()


@pytest.mark.parametrize("robot_name", ["sample-quadruped.xml", "sample-biped.xml"])
def test_support_geoms_are_the_ones_the_robot_settles_onto(robot_name: str) -> None:
    """"Foot" is measured, not declared, and both sample robots must resolve to all of theirs.

    The quadruped is the case that matters: settling it through ``reset`` returns two of
    its four shin tips, because the reset's joint noise drops it onto a diagonal pair.
    Half a support set would make ordinary standing read as unsupported contact, so this
    pins the noise-free probe rather than the reset.
    """
    env = CustomRobotEnv(
        _robot(robot_name).decode(), _setup("stand-balance", robot_name=robot_name)
    )
    try:
        names = sorted(
            mujoco.mj_id2name(env.model, mujoco.mjtObj.mjOBJ_GEOM, geom)
            for geom in env.support_geoms
        )
        assert names == (
            [
                "front_left_lower_geom",
                "front_right_lower_geom",
                "rear_left_lower_geom",
                "rear_right_lower_geom",
            ]
            if "quadruped" in robot_name
            else ["left_foot_geom", "right_foot_geom"]
        )
    finally:
        env.close()


def test_kneeling_is_scored_as_unsupported_contact() -> None:
    """The posture the user reported: knees on the floor, shins flat, torso level.

    Driven here by holding the knees at full flexion, which is what the v16 policy
    converged to.  Every instantaneous signal in the contract is happy with it -- upright
    reads 1.00 and the body is at the height v16 asked for -- so this asserts on the term
    that is not: something other than a foot is carrying the robot.
    """
    env = CustomRobotEnv(
        _robot("sample-quadruped.xml").decode(),
        _setup("stand-balance", robot_name="sample-quadruped.xml"),
    )
    try:
        env.reset(seed=11)
        names = [
            mujoco.mj_id2name(env.model, mujoco.mjtObj.mjOBJ_JOINT, int(joint_id))
            for joint_id in env.actuated_joint_ids
        ]
        folded = np.asarray(
            [0.0 if "hip" in str(name) else -2.0 for name in names], dtype=float
        )
        info: dict = {}
        for _ in range(250):
            error = folded - env.data.qpos[env.joint_qpos_adrs]
            damping = 0.6 * env.data.qvel[env.joint_dof_adrs]
            action = np.clip(6.0 * error - damping, -1.0, 1.0).astype(np.float32)
            _, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        metrics = info["task_metrics"]
        assert metrics["upright"] > 0.95, "the torso stays level, which is why upright missed this"
        assert metrics["unsupported_contact_rate"] > 0.5
        assert not metrics["success"]
    finally:
        env.close()


def _hold_pose(env: CustomRobotEnv, degrees: dict[str, float]) -> None:
    """Place the robot in a named joint configuration and rest its feet on the floor.

    Kinematic on purpose: this measures what a pose *is*, and driving the robot into one
    with a PD controller measures whether that controller can hold it, which is a
    different question and the one that made the first pass at these numbers useless.
    """
    env.data.qpos[:] = env.model.qpos0
    env.data.qvel[:] = 0.0
    for name, value in degrees.items():
        joint_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, name)
        env.data.qpos[env.model.jnt_qposadr[joint_id]] = np.radians(value)
    mujoco.mj_forward(env.model, env.data)
    lowest = min(
        float(env.data.geom_xpos[geom][2]) - float(env.model.geom_rbound[geom])
        for geom in env.support_geoms
    )
    env.data.qpos[env.root_qpos_adr + 2] -= lowest
    mujoco.mj_forward(env.model, env.data)


def test_stance_offset_separates_a_splits_from_feet_under_the_body() -> None:
    """The posture fault left after kneeling was fixed: legs splayed, but on their tips.

    Both of the earlier posture signals pass this pose.  The feet are what touch the
    ground, so ``unsupported_contact_rate`` is 0, and the torso is level at whatever
    height was asked for, so height and upright are met.  It still does not look like a
    robot standing on its legs, and this is the term that says so.

    The zigzag rows are the control: they cover the whole height range the target could
    ask for, and every one of them keeps the feet under the hips.  That is what rules out
    blaming the height target for the splay -- at no height was the robot forced into it.
    """
    env = CustomRobotEnv(
        _robot("sample-quadruped.xml").decode(),
        _setup("stand-balance", robot_name="sample-quadruped.xml"),
    )
    legs = ("front_left", "front_right", "rear_left", "rear_right")
    try:
        tolerance = float(env.contract["stance_tolerance"])
        for hip, knee in ((23.5, -47.0), (33.0, -66.0), (41.0, -82.0), (53.5, -107.0)):
            _hold_pose(
                env,
                {f"{leg}_{joint}": angle for leg in legs for joint, angle in
                 (("hip", hip), ("knee", knee))},
            )
            offset = env._stance_offset()
            assert offset < tolerance, f"feet under the hips at hip={hip} reads {offset:.3f}"
        _hold_pose(
            env,
            {f"{leg}_hip": 55.0 if leg.startswith("front") else -55.0 for leg in legs}
            | {f"{leg}_knee": 0.0 for leg in legs},
        )
        splits = env._stance_offset()
        assert splits > 0.75, splits
        assert not env._grounded_geoms(env.data) - env.support_geoms, (
            "the splits stands on its feet, which is exactly why ground contact cannot see it"
        )
    finally:
        env.close()
