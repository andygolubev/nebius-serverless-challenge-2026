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
FRAME_SKIP = 5
SERVER_TIMESTEP = 0.004
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
    if setup.get("objects") != []:
        raise CustomRobotCompatibilityError("optional-objects-not-supported")

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
        {"name": "server_light", "pos": "0 -2 6", "dir": "0 0 -1", "diffuse": "0.8 0.8 0.8"},
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
            "size": "12 12 0.1",
            "friction": "1.0 0.1 0.05",
            "rgba": "0.82 0.84 0.88 1",
        },
    )
    if scene_id == "ramp-course":
        ramp = SCENE_CONTRACTS[scene_id]["ramp"]
        assert isinstance(ramp, dict)
        pos = " ".join(str(number) for number in ramp["position"])
        size = " ".join(str(number) for number in ramp["half_size"])
        ET.SubElement(
            server_world,
            "geom",
            {
                "name": "server_ramp",
                "type": "box",
                "pos": pos,
                "size": size,
                "euler": f"0 {ramp['pitch_degrees']} 0",
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
        or model.ngeom > MAX_GEOMS + 2
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
    if (
        np.max(np.abs(model.qpos0)) > MAX_ABS_MODEL_POSITION
        or np.max(np.abs(model.body_pos)) > MAX_ABS_MODEL_POSITION
        or np.max(np.abs(model.jnt_pos)) > MAX_ABS_MODEL_POSITION
        or np.any(model.geom_size < 0)
        or np.max(model.geom_size) > MAX_GEOM_SIZE
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
        target = 0.0 if self.task_id == "stand-balance" else float(self.contract["target_velocity"])
        observation = np.concatenate(
            [
                np.asarray([height / self.initial_height], dtype=float),
                gravity,
                np.clip(velocities, -5.0, 5.0) / 5.0,
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
        self.previous_action[:] = 0
        self.steps = 0
        self.initial_x = float(self.data.qpos[self.root_qpos_adr])
        self.initial_y = float(self.data.qpos[self.root_qpos_adr + 1])
        mujoco.mj_forward(self.model, self.data)
        return self._observation(), {"reset_seed": seed}

    def step(
        self, action: np.ndarray[Any, np.dtype[np.float32]]
    ) -> tuple[np.ndarray[Any, np.dtype[np.float32]], float, bool, bool, dict[str, Any]]:
        controls = self._map_action(action)
        self.data.ctrl[:] = controls
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
            np.max(np.abs(self.data.qvel)) > MAX_ABS_QVEL
            or abs(float(self.data.qpos[self.root_qpos_adr]) - self.initial_x) > MAX_ROOT_DISTANCE
            or abs(float(self.data.qpos[self.root_qpos_adr + 1]) - self.initial_y)
            > MAX_ROOT_DISTANCE
        )
        fall_height = self.initial_height * float(self.contract["fall_height_scale"])
        fallen = height < fall_height or upright < float(self.contract["minimum_upright"])
        terminated = (not finite) or runaway or fallen
        truncated = self.steps >= int(self.contract["episode_steps"])
        target_height = self.initial_height * float(self.contract["target_height_scale"])
        height_score = math.exp(
            -(((height - target_height) / max(target_height * 0.25, 0.05)) ** 2)
        )
        action_cost = float(np.mean(np.square(np.asarray(action, dtype=float))))
        energy = float(np.mean(np.abs(controls * self.data.qvel[self.joint_dof_adrs])))
        terms: dict[str, float]
        if self.task_id == "stand-balance":
            root_motion = float(np.linalg.norm(linear) + 0.25 * np.linalg.norm(angular))
            terms = {
                "upright": max(upright, -1.0),
                "height": height_score,
                "root_motion": root_motion,
                "action": action_cost,
                "energy": energy,
            }
        else:
            terms = {
                "forward_velocity": float(linear[0]),
                "upright": max(upright, -1.0),
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
            forward_velocity=float(linear[0]),
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
                if fallen
                else "horizon"
                if truncated
                else None
            ),
        }
        return observation, reward, terminated, truncated, info

    def _success(
        self,
        *,
        upright: float,
        height: float,
        forward_velocity: float,
        lateral_drift: float,
        fallen: bool,
    ) -> bool:
        if fallen:
            return False
        if self.task_id == "stand-balance":
            target = self.initial_height * float(self.contract["target_height_scale"])
            root_speed = float(
                np.linalg.norm(self.data.qvel[self.root_dof_adr : self.root_dof_adr + 3])
            )
            return bool(
                upright >= float(self.contract["success_upright"])
                and abs(height - target)
                <= target * float(self.contract["success_height_tolerance"])
                and root_speed <= float(self.contract["success_max_root_speed"])
            )
        return bool(
            forward_velocity >= float(self.contract["success_min_velocity"])
            and lateral_drift <= float(self.contract["success_max_lateral_drift"])
        )

    def render(self) -> Any:
        if self.render_mode != "rgb_array":
            return None
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, height=480, width=640)
        self._renderer.update_scene(self.data, camera="server_camera")
        return np.asarray(self._renderer.render(), dtype=np.uint8)

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

    def factory() -> CustomRobotEnv:
        env = CustomRobotEnv(robot_xml, setup, render_mode=render_mode)
        env.reset(seed=seed + rank)
        return env

    return factory


def make_vectorized_env(
    robot_xml: str,
    setup: dict[str, Any],
    *,
    seed: int,
    n_envs: int,
) -> Any:
    if not 1 <= n_envs <= 16:
        raise ValueError("custom robot vector environment count must be 1 to 16")
    from stable_baselines3.common.vec_env import DummyVecEnv

    return DummyVecEnv(
        [make_seeded_env_factory(robot_xml, setup, seed=seed, rank=rank) for rank in range(n_envs)]
    )
