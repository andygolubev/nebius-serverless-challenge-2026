"""Generic Gymnasium/MuJoCo environment for bounded uploaded locomotion robots."""

from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, cast

import gymnasium as gym
import mujoco  # type: ignore[import-untyped]
import numpy as np
from gymnasium import spaces

from sim2policy.custom_robot_contract import (
    ADAPTER_VERSION,
    MAX_OBJECTS,
    OBSERVATION_BASE_FIELDS,
    REWARD_VERSION,
    SCENE_CONTRACTS,
    SCENE_VERSION,
    TASK_CONTRACTS,
    canonical_json,
    sha256_bytes,
)

MAX_NQ = 128
MAX_NV = 128
MAX_NU = 64
MAX_ABS_QVEL = 250.0
MAX_ROOT_DISTANCE = 20.0
# Lateral offset is reported to the policy clipped to this many metres either side of
# the start line.  Well past the drift bound the task cares about, so the observation
# keeps useful resolution near the line without saturating for a robot on its way back.
OBSERVED_LATERAL_OFFSET = 5.0
FRAME_SKIP = 5
SERVER_TIMESTEP = 0.004
# Spherical placement of the tracking video camera around the robot's root body.  The
# bearing and tilt keep the three-quarter view the static ``server_camera`` at
# pos "4 -5 2.8" gave; the distance is pulled in from that camera's 7.07 m, which was
# chosen to keep a departing robot in shot for as long as possible — a trade a tracking
# camera does not have to make.  4.5 m fills the frame with the robot, not the arena.
CAMERA_AZIMUTH_DEGREES = 128.7
CAMERA_ELEVATION_DEGREES = -22.0
CAMERA_DISTANCE = 4.5
MAX_BODIES = 64
MAX_JOINTS = 64
MAX_GEOMS = 128
MAX_XML_ELEMENTS = 512
MAX_XML_DEPTH = 16
MIN_BODY_MASS = 1e-4
MAX_BODY_MASS = 1000.0
MAX_TOTAL_MASS = 5000.0
MIN_BODY_INERTIA = 1e-10
MAX_BODY_INERTIA = 10_000.0
MAX_ABS_MODEL_POSITION = 20.0
MAX_GEOM_SIZE = 20.0
MAX_ACTUATOR_CONTROL = 1000.0
MAX_ACTUATOR_GEAR = 1000.0
MAX_ACTUATED_JOINT_RANGE = 2.0 * math.pi
_PRIMITIVE_GEOMS = {"box", "sphere", "capsule", "cylinder", "ellipsoid"}
_ALLOWED_TOP_LEVEL = {"compiler", "option", "default", "asset", "worldbody", "actuator"}
_PROHIBITED_ATTRIBUTES = {
    "assetdir",
    "dir",
    "file",
    "hfield",
    "instance",
    "mesh",
    "meshdir",
    "plugin",
    "src",
    "texture",
    "texturedir",
    "url",
}


class CustomRobotCompatibilityError(ValueError):
    """A stable preparation failure category; never include raw XML in messages."""

    def __init__(self, reason: str) -> None:
        self.reason = reason[:200]
        super().__init__(self.reason)


@dataclass(frozen=True)
class AdapterSchemas:
    observation_fields: tuple[str, ...]
    action_fields: tuple[str, ...]
    observation_sha256: str
    action_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": ADAPTER_VERSION,
            "observation_fields": list(self.observation_fields),
            "action_fields": list(self.action_fields),
            "observation_sha256": self.observation_sha256,
            "action_sha256": self.action_sha256,
            "action_normalization": "clip [-1,1], affine map to actuator ctrlrange",
            "joint_position_normalization": "affine map joint range to [-1,1]",
            "joint_velocity_normalization": "clip [-10,10] rad/s, divide by 10",
        }


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _find_single(parent: ET.Element, tag: str) -> ET.Element | None:
    values = [child for child in parent if _tag(child) == tag]
    if len(values) > 1:
        raise CustomRobotCompatibilityError(f"multiple-{tag}-sections")
    return values[0] if values else None


def _xml_depth(element: ET.Element, current: int = 1) -> int:
    children = list(element)
    return current if not children else max(_xml_depth(child, current + 1) for child in children)


def _validate_training_tree(uploaded: ET.Element) -> None:
    elements = list(uploaded.iter())
    if len(elements) > MAX_XML_ELEMENTS or _xml_depth(uploaded) > MAX_XML_DEPTH:
        raise CustomRobotCompatibilityError("xml-complexity-out-of-bounds")
    if any("}" in element.tag or ":" in element.tag for element in elements):
        raise CustomRobotCompatibilityError("xml-namespaces-not-supported")
    for child in uploaded:
        if _tag(child) not in _ALLOWED_TOP_LEVEL:
            raise CustomRobotCompatibilityError("top-level-feature-not-supported")
    for element in elements:
        tag = _tag(element)
        if tag in {"include", "plugin", "mesh", "texture", "hfield", "composite", "flexcomp"}:
            raise CustomRobotCompatibilityError("external-or-plugin-feature-not-supported")
        for attribute, value in element.attrib.items():
            if attribute.rsplit("}", 1)[-1] in _PROHIBITED_ATTRIBUTES:
                raise CustomRobotCompatibilityError("external-reference-not-supported")
            normalized = value.strip().lower().replace("\\", "/")
            if "://" in normalized or normalized.startswith(("/", "~/")) or "../" in normalized:
                raise CustomRobotCompatibilityError("external-reference-not-supported")
        if tag == "geom" and element.get("type", "sphere") not in _PRIMITIVE_GEOMS:
            raise CustomRobotCompatibilityError("geometry-type-not-supported")
        if tag in {"camera", "light", "plane"}:
            raise CustomRobotCompatibilityError("tenant-world-feature-not-supported")


def compose_server_mjcf(robot_xml: str, setup: dict[str, Any]) -> str:
    """Attach only the uploaded robot subtree to a server-owned world."""
    try:
        uploaded = ET.fromstring(robot_xml)
    except ET.ParseError as exc:
        raise CustomRobotCompatibilityError("xml-parse-failed") from exc
    if _tag(uploaded) != "mujoco":
        raise CustomRobotCompatibilityError("xml-root-unsupported")
    _validate_training_tree(uploaded)
    scene_id = str(setup.get("scene_preset_id", ""))
    if scene_id not in SCENE_CONTRACTS:
        raise CustomRobotCompatibilityError("scene-unsupported")
    objects = setup.get("objects")
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        raise CustomRobotCompatibilityError("scene-objects-invalid")

    worldbody = _find_single(uploaded, "worldbody")
    actuator = _find_single(uploaded, "actuator")
    if worldbody is None or actuator is None:
        raise CustomRobotCompatibilityError("robot-sections-missing")
    robot_bodies = [child for child in worldbody if _tag(child) == "body"]
    if len(robot_bodies) != 1:
        raise CustomRobotCompatibilityError("floating-root-count-invalid")
    if any(_tag(child) != "body" for child in worldbody):
        raise CustomRobotCompatibilityError("tenant-world-elements-not-supported")
    motors = [child for child in actuator if _tag(child) == "motor"]
    if not motors or len(motors) != len(list(actuator)):
        raise CustomRobotCompatibilityError("motor-actuators-required")

    output = ET.Element("mujoco", {"model": "sim2policy_custom_robot"})
    compiler = ET.SubElement(output, "compiler", {"autolimits": "true"})
    uploaded_compiler = _find_single(uploaded, "compiler")
    if uploaded_compiler is not None and uploaded_compiler.get("angle") in {"degree", "radian"}:
        compiler.set("angle", str(uploaded_compiler.get("angle")))
    else:
        compiler.set("angle", "radian")
    ET.SubElement(
        output,
        "option",
        {
            "gravity": "0 0 -9.81",
            "timestep": str(SERVER_TIMESTEP),
            "integrator": "RK4",
        },
    )

    uploaded_default = _find_single(uploaded, "default")
    if uploaded_default is not None:
        output.append(copy.deepcopy(uploaded_default))
    uploaded_asset = _find_single(uploaded, "asset")
    if uploaded_asset is not None:
        asset = ET.SubElement(output, "asset")
        for child in uploaded_asset:
            if _tag(child) != "material":
                raise CustomRobotCompatibilityError("external-assets-not-supported")
            asset.append(copy.deepcopy(child))

    server_world = ET.SubElement(output, "worldbody")
    ET.SubElement(
        server_world,
        "light",
        # Directional rather than positional: a point light at a fixed spot lit a pool of
        # floor around the spawn point, so a robot that walked out of that pool got
        # steadily darker in the video.  A directional light does not attenuate, so the
        # whole arena is lit the same wherever the robot ends up.
        {
            "name": "server_light",
            "directional": "true",
            "pos": "0 -2 6",
            "dir": "0 0.3 -1",
            "diffuse": "0.8 0.8 0.8",
        },
    )
    ET.SubElement(
        server_world,
        "camera",
        {
            "name": "server_camera",
            "pos": "4 -5 2.8",
            "xyaxes": "0.78 0.62 0 -0.24 0.30 0.92",
        },
    )
    ET.SubElement(
        server_world,
        "geom",
        {
            "name": "server_floor",
            "type": "plane",
            # Drawn extent only — a MuJoCo plane collides as an infinite half-space
            # whatever its size, so this changes what the video shows and nothing about
            # the physics.  12 m was wider than the static camera could see; a
            # walk-forward policy at the commanded 0.8 m/s covers 16 m in one episode,
            # so with a camera that follows the robot the old extent ran out mid-clip
            # and left it walking over a black void.
            "size": "30 30 0.1",
            "friction": "1.0 0.1 0.05",
            "rgba": "0.82 0.84 0.88 1",
        },
    )
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            raise CustomRobotCompatibilityError("scene-object-invalid")
        object_type = str(item.get("object_type", ""))
        try:
            x, y, z = (float(item[name]) for name in ("x", "y", "z"))
            yaw = math.radians(float(item["yaw_degrees"]))
            width, depth, height = (
                float(item[name]) for name in ("width", "depth", "height")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CustomRobotCompatibilityError("scene-object-invalid") from exc
        pitch = -math.atan2(height, depth) if object_type == "ramp" else 0.0
        half_x = math.hypot(depth, height) / 2.0 if object_type == "ramp" else depth / 2.0
        half_z = 0.05 if object_type == "ramp" else height / 2.0
        cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
        cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
        quaternion = (cy * cp, -sy * sp, cy * sp, sy * cp)
        ET.SubElement(
            server_world,
            "geom",
            {
                "name": f"server_object_{index}_{object_type}",
                "type": "box",
                "pos": f"{x} {y} {z + height / 2.0}",
                "size": f"{half_x} {width / 2.0} {half_z}",
                "quat": " ".join(str(value) for value in quaternion),
                "friction": "1.0 0.1 0.05",
                "rgba": "0.35 0.38 0.46 1",
            },
        )
    server_world.append(copy.deepcopy(robot_bodies[0]))
    output_actuator = ET.SubElement(output, "actuator")
    for motor in motors:
        output_actuator.append(copy.deepcopy(motor))
    return ET.tostring(output, encoding="unicode")


def _all_finite(value: np.ndarray[Any, Any]) -> bool:
    return bool(np.isfinite(value).all())


def compile_model(robot_xml: str, setup: dict[str, Any]) -> tuple[mujoco.MjModel, str]:
    composed = compose_server_mjcf(robot_xml, setup)
    try:
        model = mujoco.MjModel.from_xml_string(composed)
    except Exception as exc:
        raise CustomRobotCompatibilityError("mujoco-compile-failed") from exc
    if (
        model.nq > MAX_NQ
        or model.nv > MAX_NV
        or model.nu > MAX_NU
        or model.nu < 1
        or model.nbody - 1 > MAX_BODIES
        or model.njnt > MAX_JOINTS
        or model.ngeom > MAX_GEOMS + 1 + MAX_OBJECTS
    ):
        raise CustomRobotCompatibilityError("compiled-dimensions-out-of-bounds")
    arrays = (
        model.qpos0,
        model.body_pos,
        model.body_quat,
        model.body_mass,
        model.body_inertia,
        model.geom_size,
        model.jnt_pos,
        model.jnt_range,
        model.actuator_ctrlrange,
        model.actuator_gear,
    )
    if not all(_all_finite(np.asarray(value)) for value in arrays):
        raise CustomRobotCompatibilityError("compiled-values-non-finite")
    robot_mass = np.asarray(model.body_mass[1:])
    robot_inertia = np.asarray(model.body_inertia[1:])
    if (
        np.any(robot_mass < MIN_BODY_MASS)
        or np.any(robot_mass > MAX_BODY_MASS)
        or float(np.sum(robot_mass)) > MAX_TOTAL_MASS
        or np.any(robot_inertia < MIN_BODY_INERTIA)
        or np.any(robot_inertia > MAX_BODY_INERTIA)
    ):
        raise CustomRobotCompatibilityError("compiled-mass-inertia-invalid")
    # ``MAX_GEOM_SIZE`` bounds what a tenant may upload or place, so it is measured over
    # every geom except the arena floor the server itself writes: that plane is drawn
    # wide enough to stay under a walking robot for a full episode, which is a rendering
    # decision the server owns rather than tenant data to be validated.
    floor_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "server_floor")
    tenant_geom_sizes = (
        np.delete(model.geom_size, floor_geom, axis=0)
        if floor_geom >= 0
        else model.geom_size
    )
    if (
        np.max(np.abs(model.qpos0)) > MAX_ABS_MODEL_POSITION
        or np.max(np.abs(model.body_pos)) > MAX_ABS_MODEL_POSITION
        or np.max(np.abs(model.jnt_pos)) > MAX_ABS_MODEL_POSITION
        or np.any(model.geom_size < 0)
        or (tenant_geom_sizes.size > 0 and np.max(tenant_geom_sizes) > MAX_GEOM_SIZE)
    ):
        raise CustomRobotCompatibilityError("compiled-geometry-out-of-bounds")
    if not np.all(np.asarray(model.actuator_ctrllimited, dtype=bool)):
        raise CustomRobotCompatibilityError("actuator-control-range-required")
    if (
        np.any(model.actuator_ctrlrange[:, 0] >= model.actuator_ctrlrange[:, 1])
        or np.max(np.abs(model.actuator_ctrlrange)) > MAX_ACTUATOR_CONTROL
    ):
        raise CustomRobotCompatibilityError("actuator-control-range-invalid")
    if (
        np.any(np.abs(model.actuator_gear[:, 0]) < 1e-8)
        or np.max(np.abs(model.actuator_gear)) > MAX_ACTUATOR_GEAR
    ):
        raise CustomRobotCompatibilityError("actuator-gear-invalid")
    for actuator_id in range(model.nu):
        joint_id = int(model.actuator_trnid[actuator_id, 0])
        if joint_id < 0 or model.jnt_type[joint_id] != mujoco.mjtJoint.mjJNT_HINGE:
            raise CustomRobotCompatibilityError("actuated-hinge-required")
        if not bool(model.jnt_limited[joint_id]):
            raise CustomRobotCompatibilityError("actuated-joint-range-required")
        joint_range = model.jnt_range[joint_id]
        if not 1e-6 <= joint_range[1] - joint_range[0] <= MAX_ACTUATED_JOINT_RANGE:
            raise CustomRobotCompatibilityError("actuated-joint-range-invalid")
    free_joints = np.where(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)[0]
    if len(free_joints) != 1:
        raise CustomRobotCompatibilityError("floating-root-count-invalid")
    return model, composed


class CustomRobotEnv(
    gym.Env[
        np.ndarray[Any, np.dtype[np.float32]],
        np.ndarray[Any, np.dtype[np.float32]],
    ]
):
    metadata = {"render_modes": ["rgb_array"], "render_fps": 50}

    def __init__(
        self,
        robot_xml: str,
        setup: dict[str, Any],
        *,
        render_mode: str | None = None,
    ) -> None:
        super().__init__()
        if render_mode not in {None, "rgb_array"}:
            raise ValueError("custom robot runtime supports rgb_array rendering only")
        self.model, self.composed_xml = compile_model(robot_xml, setup)
        self.data = mujoco.MjData(self.model)
        self.render_mode = render_mode
        self._renderer: mujoco.Renderer | None = None
        self._tracking_camera: Any = None
        self.task_id = str(setup["task_template_id"])
        if self.task_id not in TASK_CONTRACTS:
            raise CustomRobotCompatibilityError("task-unsupported")
        self.scene_id = str(setup["scene_preset_id"])
        self.contract = TASK_CONTRACTS[self.task_id]
        free_joint = int(np.where(self.model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)[0][0])
        self.root_body_id = int(self.model.jnt_bodyid[free_joint])
        self.root_qpos_adr = int(self.model.jnt_qposadr[free_joint])
        self.root_dof_adr = int(self.model.jnt_dofadr[free_joint])
        self.actuated_joint_ids = np.asarray(self.model.actuator_trnid[:, 0], dtype=np.int32)
        self.joint_qpos_adrs = np.asarray(
            [self.model.jnt_qposadr[joint_id] for joint_id in self.actuated_joint_ids],
            dtype=np.int32,
        )
        self.joint_dof_adrs = np.asarray(
            [self.model.jnt_dofadr[joint_id] for joint_id in self.actuated_joint_ids],
            dtype=np.int32,
        )
        self.joint_ranges = np.asarray(self.model.jnt_range[self.actuated_joint_ids], dtype=float)
        self.ctrl_ranges = np.asarray(self.model.actuator_ctrlrange, dtype=float)
        self.initial_qpos = self.model.qpos0.copy()
        self.initial_height = float(self.initial_qpos[self.root_qpos_adr + 2])
        if not 0.1 <= self.initial_height <= 5.0:
            raise CustomRobotCompatibilityError("initial-root-height-out-of-bounds")
        # Replaced with the settled height on every reset (see ``reset``); the spawn
        # height is only the fallback for tasks that reset into a non-standing pose.
        self.reference_height = self.initial_height
        self.previous_action = np.zeros(self.model.nu, dtype=np.float32)
        self.steps = 0
        self.initial_x = float(self.initial_qpos[self.root_qpos_adr])
        self.initial_y = float(self.initial_qpos[self.root_qpos_adr + 1])
        self.action_space = spaces.Box(-1.0, 1.0, shape=(self.model.nu,), dtype=np.float32)
        self.schemas = self._build_schemas()
        self.observation_space = spaces.Box(
            -10.0,
            10.0,
            shape=(len(self.schemas.observation_fields),),
            dtype=np.float32,
        )
        mujoco.mj_forward(self.model, self.data)

    def _build_schemas(self) -> AdapterSchemas:
        joint_names = [
            mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, int(joint_id))
            or f"joint_{joint_id}"
            for joint_id in self.actuated_joint_ids
        ]
        actuator_names = [
            mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_id)
            or f"actuator_{actuator_id}"
            for actuator_id in range(self.model.nu)
        ]
        observation = (
            *OBSERVATION_BASE_FIELDS,
            *(f"joint.{name}.position" for name in joint_names),
            *(f"joint.{name}.velocity" for name in joint_names),
            *(f"previous_action.{name}" for name in actuator_names),
            "task.target",
        )
        actions = tuple(f"actuator.{name}" for name in actuator_names)
        return AdapterSchemas(
            observation_fields=tuple(observation),
            action_fields=actions,
            observation_sha256=sha256_bytes(canonical_json(list(observation))),
            action_sha256=sha256_bytes(canonical_json(list(actions))),
        )

    def _root_features(self) -> tuple[float, float, np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        root_matrix = self.data.xmat[self.root_body_id].reshape(3, 3)
        upright = float(root_matrix[2, 2])
        gravity = root_matrix.T @ np.asarray([0.0, 0.0, -1.0])
        linear = root_matrix.T @ self.data.qvel[self.root_dof_adr : self.root_dof_adr + 3]
        angular = root_matrix.T @ self.data.qvel[self.root_dof_adr + 3 : self.root_dof_adr + 6]
        height = float(self.data.qpos[self.root_qpos_adr + 2])
        return height, upright, np.concatenate([linear, angular]), gravity

    def _observation(self) -> np.ndarray[Any, np.dtype[np.float32]]:
        height, _, velocities, gravity = self._root_features()
        low = self.joint_ranges[:, 0]
        high = self.joint_ranges[:, 1]
        positions = self.data.qpos[self.joint_qpos_adrs]
        normalized_positions = np.clip(2.0 * (positions - low) / (high - low) - 1.0, -1.0, 1.0)
        normalized_velocities = np.clip(self.data.qvel[self.joint_dof_adrs], -10.0, 10.0) / 10.0
        target = (
            float(self.contract["target_velocity"])
            if self.task_id == "walk-forward"
            else 0.0
        )
        # Course state, in the frame the task is defined in.  Offset is clipped at the
        # runaway bound and scaled into roughly [-1, 1] like the rest of the vector;
        # heading is given as cos/sin so it stays continuous across the +/-pi wrap.
        root_matrix = self.data.xmat[self.root_body_id].reshape(3, 3)
        heading = math.atan2(float(root_matrix[1, 0]), float(root_matrix[0, 0]))
        lateral_offset = float(self.data.qpos[self.root_qpos_adr + 1]) - self.initial_y
        course = np.asarray(
            [
                np.clip(lateral_offset, -OBSERVED_LATERAL_OFFSET, OBSERVED_LATERAL_OFFSET)
                / OBSERVED_LATERAL_OFFSET,
                math.cos(heading),
                math.sin(heading),
            ],
            dtype=float,
        )
        observation = np.concatenate(
            [
                np.asarray([height / self.reference_height], dtype=float),
                gravity,
                np.clip(velocities, -5.0, 5.0) / 5.0,
                course,
                normalized_positions,
                normalized_velocities,
                self.previous_action,
                np.asarray([target], dtype=float),
            ]
        ).astype(np.float32)
        if not _all_finite(observation):
            raise CustomRobotCompatibilityError("observation-non-finite")
        return cast(np.ndarray[Any, np.dtype[np.float32]], observation)

    def _map_action(self, action: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        clipped = np.clip(np.asarray(action, dtype=float), -1.0, 1.0)
        low = self.ctrl_ranges[:, 0]
        high = self.ctrl_ranges[:, 1]
        controls = low + (clipped + 1.0) * 0.5 * (high - low)
        if not _all_finite(controls):
            raise CustomRobotCompatibilityError("action-non-finite")
        return cast(np.ndarray[Any, Any], controls)

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray[Any, np.dtype[np.float32]], dict[str, Any]]:
        del options
        super().reset(seed=seed)
        self.data.qpos[:] = self.initial_qpos
        self.data.qvel[:] = 0
        assert self.np_random is not None
        self.data.qpos[self.joint_qpos_adrs] += self.np_random.uniform(
            -0.02, 0.02, size=len(self.joint_qpos_adrs)
        )
        self.data.qvel[self.joint_dof_adrs] = self.np_random.uniform(
            -0.02, 0.02, size=len(self.joint_dof_adrs)
        )
        if self.task_id == "recover-from-fall":
            low, high = self.contract["reset_roll_radians"]
            roll = float(self.np_random.uniform(float(low), float(high)))
            if float(self.np_random.uniform()) < 0.5:
                roll = -roll
            self.data.qpos[self.root_qpos_adr + 2] = max(
                0.12,
                self.initial_height * float(self.contract["reset_height_scale"]),
            )
            self.data.qpos[self.root_qpos_adr + 3 : self.root_qpos_adr + 7] = (
                math.cos(roll / 2.0), math.sin(roll / 2.0), 0.0, 0.0
            )
        self.previous_action[:] = 0
        self.steps = 0
        mujoco.mj_forward(self.model, self.data)
        # Let the model settle onto the floor under zero control before the episode
        # starts.  ``initial_height`` is the height the author wrote into the MJCF, not
        # the height the robot actually rests at; deriving the fall threshold from the
        # spawn height terminated episodes during the drop, before the policy acted.
        # ``recover-from-fall`` sets settle_steps to 0: it resets into a deliberately
        # fallen pose, so its height references must stay the upright spawn height.
        settle_steps = int(self.contract.get("settle_steps", 0))
        if settle_steps > 0:
            self.data.ctrl[:] = 0
            for _ in range(settle_steps * FRAME_SKIP):
                mujoco.mj_step(self.model, self.data)
            self.data.qvel[:] = 0
            mujoco.mj_forward(self.model, self.data)
            self.reference_height = float(self.data.qpos[self.root_qpos_adr + 2])
        else:
            self.reference_height = self.initial_height
        self.initial_x = float(self.data.qpos[self.root_qpos_adr])
        self.initial_y = float(self.data.qpos[self.root_qpos_adr + 1])
        return self._observation(), {"reset_seed": seed}

    def step(
        self, action: np.ndarray[Any, np.dtype[np.float32]]
    ) -> tuple[np.ndarray[Any, np.dtype[np.float32]], float, bool, bool, dict[str, Any]]:
        controls = self._map_action(action)
        self.data.ctrl[:] = controls
        # Sampled before the substeps as well: contact with the floor can absorb an
        # exploding velocity within the frame skip and hide the divergence that the
        # runaway guard exists to catch.
        entry_qvel = float(np.max(np.abs(self.data.qvel)))
        for _ in range(FRAME_SKIP):
            mujoco.mj_step(self.model, self.data)
        self.steps += 1
        height, upright, velocities, _ = self._root_features()
        linear = velocities[:3]
        angular = velocities[3:]
        finite = all(
            _all_finite(np.asarray(value))
            for value in (self.data.qpos, self.data.qvel, self.data.ctrl)
        )
        runaway = bool(
            max(entry_qvel, float(np.max(np.abs(self.data.qvel)))) > MAX_ABS_QVEL
            or abs(float(self.data.qpos[self.root_qpos_adr]) - self.initial_x) > MAX_ROOT_DISTANCE
            or abs(float(self.data.qpos[self.root_qpos_adr + 1]) - self.initial_y)
            > MAX_ROOT_DISTANCE
        )
        fall_height = self.reference_height * float(self.contract["fall_height_scale"])
        fallen = height < fall_height or upright < float(self.contract["minimum_upright"])
        fall_terminates = fallen and self.task_id != "recover-from-fall"
        terminated = (not finite) or runaway or fall_terminates
        truncated = self.steps >= int(self.contract["episode_steps"])
        target_height = self.reference_height * float(self.contract["target_height_scale"])
        height_score = math.exp(
            -(((height - target_height) / max(target_height * 0.25, 0.05)) ** 2)
        )
        action_cost = float(np.mean(np.square(np.asarray(action, dtype=float))))
        energy = float(np.mean(np.abs(controls * self.data.qvel[self.joint_dof_adrs])))
        terms: dict[str, float]
        # Paid for every step the robot has not terminated.  Without it the only signal
        # against falling is the -1.0 terminal penalty, which a step of forward motion
        # already outweighs, so early failure costs the policy almost nothing.
        alive = 0.0 if terminated else 1.0
        if self.task_id in {"stand-balance", "recover-from-fall"}:
            root_motion = float(np.linalg.norm(linear) + 0.25 * np.linalg.norm(angular))
            terms = {
                "alive": alive,
                "upright": max(upright, -1.0),
                "height": height_score,
                "root_motion": root_motion,
                "action": action_cost,
                "energy": energy,
            }
        else:
            # Score velocity against the commanded target instead of rewarding raw
            # magnitude: unbounded velocity paid more for diving forward than for
            # walking, so policies learned to fall in the commanded direction.
            target_velocity = float(self.contract["target_velocity"])
            tolerance = max(float(self.contract["velocity_tolerance"]), 1e-6)
            velocity_score = math.exp(
                -(((float(linear[0]) - target_velocity) / tolerance) ** 2)
            )
            # Success bounds accumulated lateral *displacement*, but v5 priced only
            # lateral velocity and yaw rate — both derivatives.  A bias too small to be
            # worth correcting on any single step integrates over a 20 s episode into
            # metres of drift: measured runs walked the full horizon at the commanded
            # speed and still ended 4-13 m off the line.  Scoring the offset itself
            # closes that gap.  Bounded like the velocity term so that a policy far off
            # course cannot be driven to give up walking to cut its losses.
            lateral_tolerance = max(float(self.contract["lateral_tolerance"]), 1e-6)
            lateral_offset = abs(
                float(self.data.qpos[self.root_qpos_adr + 1]) - self.initial_y
            )
            # Deliberately not a Gaussian like the velocity term: exp(-(d/0.75)^2) is
            # already flat to five decimal places by three metres out, so a policy that
            # had drifted saw no gradient back towards the line and none distinguishing
            # three metres off from twelve.  This form decays polynomially — bounded in
            # [0, 1], but with a pull home at any distance.
            lateral_offset_score = 1.0 / (1.0 + (lateral_offset / lateral_tolerance) ** 2)
            terms = {
                "alive": alive,
                "forward_velocity": velocity_score,
                "upright": max(upright, -1.0),
                # Holding a walking height is scored here as well as in stand-balance:
                # without it the only floor under the body was the fall line itself.
                "height": height_score,
                "lateral_offset": lateral_offset_score,
                "lateral_velocity": abs(float(linear[1])),
                "yaw_rate": abs(float(angular[2])),
                "action": action_cost,
                "energy": energy,
            }
        weights = self.contract["weights"]
        reward = float(sum(float(weights[name]) * value for name, value in terms.items()))
        if terminated:
            reward -= 1.0
        self.previous_action = np.clip(np.asarray(action, dtype=np.float32), -1, 1)
        observation_shape = self.observation_space.shape
        assert observation_shape is not None
        observation = self._observation() if finite else np.zeros(observation_shape, np.float32)
        x = float(self.data.qpos[self.root_qpos_adr])
        y = float(self.data.qpos[self.root_qpos_adr + 1])
        success = self._success(
            upright=upright,
            height=height,
            lateral_drift=abs(y - self.initial_y),
            fallen=fallen,
        )
        info = {
            "task": self.task_id,
            "reward_terms": terms,
            "task_metrics": {
                "root_height": height,
                "upright": upright,
                "forward_velocity": float(linear[0]),
                "mean_forward_velocity": self.mean_forward_velocity,
                "lateral_drift": abs(y - self.initial_y),
                "forward_progress": x - self.initial_x,
                "fallen": fallen,
                "non_finite": not finite,
                "runaway": runaway,
                "success": success,
            },
            "termination_reason": (
                "non_finite"
                if not finite
                else "runaway"
                if runaway
                else "fall"
                if fall_terminates
                else "horizon"
                if truncated
                else None
            ),
        }
        return observation, reward, terminated, truncated, info

    @property
    def mean_forward_velocity(self) -> float:
        """Average forward speed over the episode so far, in metres per second.

        Taken from net root displacement rather than from a running average of the
        per-step velocity, so a gait that rocks the root backwards and forwards within a
        stride is scored on the ground it actually covered.
        """
        elapsed = self.steps * FRAME_SKIP * SERVER_TIMESTEP
        if elapsed <= 0.0:
            return 0.0
        return (float(self.data.qpos[self.root_qpos_adr]) - self.initial_x) / elapsed

    def _success(
        self,
        *,
        upright: float,
        height: float,
        lateral_drift: float,
        fallen: bool,
    ) -> bool:
        if fallen:
            return False
        if self.task_id in {"stand-balance", "recover-from-fall"}:
            target = self.reference_height * float(self.contract["target_height_scale"])
            root_speed = float(
                np.linalg.norm(self.data.qvel[self.root_dof_adr : self.root_dof_adr + 3])
            )
            height_requirement = (
                self.reference_height * float(self.contract["success_height_scale"])
                if self.task_id == "recover-from-fall"
                else target * (1.0 - float(self.contract["success_height_tolerance"]))
            )
            height_ok = (
                height >= height_requirement
                if self.task_id == "recover-from-fall"
                else abs(height - target)
                <= target * float(self.contract["success_height_tolerance"])
            )
            return bool(
                upright >= float(self.contract["success_upright"])
                and height_ok
                and root_speed <= float(self.contract["success_max_root_speed"])
            )
        # walk-forward is scored over the episode, not at the instant the episode ends.
        # v4 read the root's instantaneous forward velocity at the final step, but a
        # legged gait's root velocity oscillates within every stride and passes near
        # zero at each foot-strike, so even a robot averaging the commanded 0.8 m/s
        # samples below the 0.35 bar at a large fraction of steps.  Requiring that
        # coin-flip to land 20 times in a row made ``task_threshold_achieved``
        # unreachable for any gait: the measured run walked for the full horizon in 16
        # of 20 episodes and still scored 15%.  The episode-mean form below states the
        # same intent — sustained forward travel in a straight line — and is stricter in
        # the ways that matter, because it also requires the robot to survive to the
        # horizon rather than to look good on one lucky timestep.
        return bool(
            self.steps >= int(self.contract["episode_steps"])
            and self.mean_forward_velocity >= float(self.contract["success_min_velocity"])
            and lateral_drift <= float(self.contract["success_max_lateral_drift"])
        )

    def render(self) -> Any:
        if self.render_mode != "rgb_array":
            return None
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, height=480, width=640)
        self._renderer.update_scene(self.data, camera=self._camera())
        return np.asarray(self._renderer.render(), dtype=np.uint8)

    def _camera(self) -> Any:
        """A camera that tracks the robot instead of watching a fixed patch of floor.

        ``server_camera`` is a static worldbody camera, so a walk-forward policy that
        works simply leaves frame — the better the policy, the less of it is visible.
        This keeps that camera's three-quarter view but locks it onto the root body, so
        the robot stays centred for the whole clip.  Built here as a render-time
        ``MjvCamera`` rather than as an MJCF tracking camera because which way the video
        looks is a property of the recording, not of the scene the policy trains in.
        """
        if self._tracking_camera is None:
            camera = mujoco.MjvCamera()
            camera.type = mujoco.mjtCamera.mjCAMERA_TRACKING
            camera.trackbodyid = self.root_body_id
            camera.azimuth = CAMERA_AZIMUTH_DEGREES
            camera.elevation = CAMERA_ELEVATION_DEGREES
            camera.distance = CAMERA_DISTANCE
            self._tracking_camera = camera
        return self._tracking_camera

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def resolved_contract(self) -> dict[str, Any]:
        return {
            "adapter_version": ADAPTER_VERSION,
            "reward_version": REWARD_VERSION,
            "scene_version": SCENE_VERSION,
            "task": self.task_id,
            "scene": self.scene_id,
            "frame_skip": FRAME_SKIP,
            "timestep": SERVER_TIMESTEP,
            "episode_steps": int(self.contract["episode_steps"]),
            "task_contract": self.contract,
            "scene_contract": SCENE_CONTRACTS[self.scene_id],
            "schemas": self.schemas.to_dict(),
            "compiled": {
                "nq": self.model.nq,
                "nv": self.model.nv,
                "nu": self.model.nu,
                "body_count": self.model.nbody - 1,
                "joint_count": self.model.njnt,
                "geom_count": self.model.ngeom,
                "initial_root_height": self.initial_height,
            },
        }


def make_custom_env(
    robot_xml: str,
    setup: dict[str, Any],
    *,
    render_mode: str | None = None,
) -> CustomRobotEnv:
    return CustomRobotEnv(robot_xml, setup, render_mode=render_mode)


def make_seeded_env_factory(
    robot_xml: str,
    setup: dict[str, Any],
    *,
    seed: int,
    rank: int = 0,
    render_mode: str | None = None,
) -> Any:
    """Return the picklable-style factory expected by SB3 vector environments."""

    def factory() -> Any:
        from stable_baselines3.common.monitor import Monitor

        env = CustomRobotEnv(robot_xml, setup, render_mode=render_mode)
        env.reset(seed=seed + rank)
        # Monitor is what populates ``info["episode"]``; without it SB3 reports no
        # episode statistics at all and the published reward curve stays empty.
        return Monitor(env)

    return factory


def make_vectorized_env(
    robot_xml: str,
    setup: dict[str, Any],
    *,
    seed: int,
    n_envs: int,
) -> Any:
    """Build the training vector environment.

    Uses subprocess workers whenever more than one environment is requested: the
    training preset provisions many vCPUs, and a serial ``DummyVecEnv`` would leave all
    but one of them idle.
    """
    if not 1 <= n_envs <= 16:
        raise ValueError("custom robot vector environment count must be 1 to 16")
    from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

    factories = [
        make_seeded_env_factory(robot_xml, setup, seed=seed, rank=rank)
        for rank in range(n_envs)
    ]
    if n_envs == 1:
        return DummyVecEnv(factories)
    # Default start method: forkserver where available, otherwise spawn.  Both re-import
    # the entry module in the worker, which is safe because ``custom_robot_job`` guards
    # its CLI behind ``__main__``; plain fork is avoided because the parent has already
    # initialised torch.
    return SubprocVecEnv(factories)
