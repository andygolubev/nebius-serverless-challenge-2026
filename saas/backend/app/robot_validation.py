"""Deterministic, dependency-free validation for constrained tenant MJCF uploads."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from .models import ValidationSummary

MAX_ROBOT_BYTES = 1024 * 1024
MAX_BODIES = 64
MAX_JOINTS = 64
MAX_ACTUATORS = 64
MAX_GEOMS = 128
MAX_XML_DEPTH = 16

_DECLARATION = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_ALLOWED_ELEMENTS = {
    "mujoco",
    "compiler",
    "option",
    "size",
    "statistic",
    "default",
    "asset",
    "material",
    "worldbody",
    "body",
    "inertial",
    "freejoint",
    "joint",
    "geom",
    "site",
    "contact",
    "exclude",
    "actuator",
    "motor",
    "position",
    "velocity",
    "general",
    "equality",
    "connect",
    "weld",
}
_PROHIBITED_ELEMENTS = {
    "include",
    "plugin",
    "mesh",
    "texture",
    "hfield",
    "composite",
    "flexcomp",
}
_PROHIBITED_ATTRIBUTES = {
    "file",
    "dir",
    "meshdir",
    "texturedir",
    "assetdir",
    "mesh",
    "texture",
    "hfield",
    "plugin",
    "instance",
    "url",
    "src",
    "tendon",
    "cranksite",
    "slidersite",
}
_PRIMITIVE_GEOMS = {"box", "sphere", "capsule", "cylinder", "ellipsoid"}
_ACTUATOR_ELEMENTS = {"motor", "position", "velocity", "general"}


class RobotValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def _tag(element: ET.Element) -> str:
    if "}" in element.tag:
        return element.tag.rsplit("}", 1)[1]
    return element.tag


def _depth(element: ET.Element, current: int = 1) -> int:
    if not list(element):
        return current
    return max(_depth(child, current + 1) for child in element)


def _require_unique_names(
    elements: list[ET.Element], namespace: str, *, required: bool
) -> list[str]:
    names: list[str] = []
    for element in elements:
        name = (element.get("name") or "").strip()
        if required and not name:
            raise RobotValidationError("file", f"every {namespace} must have a name")
        if not name:
            continue
        if name in names:
            raise RobotValidationError("file", f"duplicate {namespace} name: {name}")
        names.append(name)
    return names


def _bounded_count(name: str, value: int, limit: int) -> None:
    if value > limit:
        raise RobotValidationError("file", f"{name} limit is {limit}; received {value}")


def validate_mjcf(raw: bytes) -> tuple[str, str, ValidationSummary]:
    """Validate bytes and return decoded XML, SHA-256 digest, and structural summary."""
    if not raw:
        raise RobotValidationError("file", "MJCF file is empty")
    if len(raw) > MAX_ROBOT_BYTES:
        raise RobotValidationError("file", "MJCF file must be at most 1 MiB")
    if raw.startswith((b"PK\x03\x04", b"\x1f\x8b")):
        raise RobotValidationError(
            "file", "archives are not supported; upload one .xml file"
        )
    if _DECLARATION.search(raw):
        raise RobotValidationError(
            "file", "DTD and entity declarations are not supported"
        )
    try:
        xml_content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RobotValidationError("file", "MJCF must be valid UTF-8") from exc
    if "\x00" in xml_content:
        raise RobotValidationError(
            "file", "MJCF contains an unsupported control character"
        )
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise RobotValidationError("file", "MJCF is not well-formed XML") from exc

    if root.tag != "mujoco":
        raise RobotValidationError(
            "file", "root element must be <mujoco> without a namespace"
        )
    depth = _depth(root)
    if depth > MAX_XML_DEPTH:
        raise RobotValidationError(
            "file", f"XML depth limit is {MAX_XML_DEPTH}; received {depth}"
        )

    for element in root.iter():
        tag = _tag(element)
        if tag in _PROHIBITED_ELEMENTS:
            raise RobotValidationError("file", f"<{tag}> is not supported")
        if tag not in _ALLOWED_ELEMENTS:
            raise RobotValidationError(
                "file", f"<{tag}> is outside the supported robot contract"
            )
        for attribute, value in element.attrib.items():
            local_attribute = attribute.rsplit("}", 1)[-1]
            if local_attribute in _PROHIBITED_ATTRIBUTES:
                raise RobotValidationError(
                    "file", f"attribute {local_attribute!r} is not supported"
                )
            normalized_value = value.strip().lower().replace("\\", "/")
            if (
                "://" in normalized_value
                or normalized_value.startswith(("/", "~/"))
                or "../" in normalized_value
            ):
                raise RobotValidationError(
                    "file", "external paths and remote references are not supported"
                )

    worldbodies = [element for element in root if _tag(element) == "worldbody"]
    if len(worldbodies) != 1:
        raise RobotValidationError("file", "MJCF must contain exactly one <worldbody>")
    root_bodies = [element for element in worldbodies[0] if _tag(element) == "body"]
    if len(root_bodies) != 1:
        raise RobotValidationError(
            "file", "worldbody must contain exactly one floating robot root body"
        )

    bodies = [element for element in root.iter() if _tag(element) == "body"]
    joints = [
        element for element in root.iter() if _tag(element) in {"joint", "freejoint"}
    ]
    geoms = [element for element in root.iter() if _tag(element) == "geom"]
    actuator_containers = [element for element in root if _tag(element) == "actuator"]
    actuator_elements = [
        child
        for container in actuator_containers
        for child in container
        if _tag(child) in _ACTUATOR_ELEMENTS
    ]
    _bounded_count("body", len(bodies), MAX_BODIES)
    _bounded_count("joint", len(joints), MAX_JOINTS)
    _bounded_count("actuator", len(actuator_elements), MAX_ACTUATORS)
    _bounded_count("geom", len(geoms), MAX_GEOMS)

    _require_unique_names(bodies, "body", required=True)
    joint_names = _require_unique_names(joints, "joint", required=True)
    _require_unique_names(geoms, "geom", required=False)
    actuator_names = _require_unique_names(actuator_elements, "actuator", required=True)

    for geom in geoms:
        geom_type = geom.get("type", "sphere")
        if geom_type not in _PRIMITIVE_GEOMS:
            raise RobotValidationError(
                "file", f"geometry type {geom_type!r} is not supported"
            )

    all_free_joints = [
        element
        for element in joints
        if _tag(element) == "freejoint" or element.get("type") == "free"
    ]
    root_free_joints = [
        element
        for element in root_bodies[0]
        if _tag(element) == "freejoint"
        or (_tag(element) == "joint" and element.get("type") == "free")
    ]
    if len(all_free_joints) != 1 or len(root_free_joints) != 1:
        raise RobotValidationError(
            "file", "robot must have one free joint directly on its root body"
        )

    hinge_names = {
        element.get("name", "")
        for element in joints
        if _tag(element) == "joint" and element.get("type", "hinge") == "hinge"
    }
    if not hinge_names:
        raise RobotValidationError(
            "file", "robot must contain at least one named hinge joint"
        )
    if not actuator_elements:
        raise RobotValidationError(
            "file", "robot must contain at least one joint actuator"
        )
    referenced: set[str] = set()
    for actuator in actuator_elements:
        reference = (actuator.get("joint") or "").strip()
        if not reference:
            raise RobotValidationError("file", "every actuator must reference a joint")
        if reference not in joint_names:
            name = actuator.get("name", "unnamed")
            raise RobotValidationError(
                "file", f"actuator {name!r} references unknown joint {reference!r}"
            )
        referenced.add(reference)
    if not (hinge_names & referenced):
        raise RobotValidationError(
            "file", "at least one hinge joint must be controllable by an actuator"
        )

    summary = ValidationSummary(
        body_count=len(bodies),
        joint_count=len(joints),
        actuator_count=len(actuator_elements),
        geom_count=len(geoms),
        joint_names=sorted(joint_names),
        actuator_names=sorted(actuator_names),
    )
    return xml_content, hashlib.sha256(raw).hexdigest(), summary
