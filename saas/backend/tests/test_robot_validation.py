"""Security and structural boundaries for the public MJCF validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.robot_validation import MAX_ROBOT_BYTES, RobotValidationError, validate_mjcf

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "robots"


def _robot(
    *, inner: str = "", actuator: str = '<motor name="motor" joint="hinge"/>'
) -> bytes:
    return f"""<mujoco><worldbody><body name="root"><freejoint name="free"/>
      <joint name="hinge" type="hinge"/><geom name="body_geom" type="box"/>{inner}
      </body></worldbody><actuator>{actuator}</actuator></mujoco>""".encode()


def test_canonical_samples_pass_the_public_validator():
    results = {}
    for path in sorted(SAMPLES.glob("*.xml")):
        content, digest, summary = validate_mjcf(path.read_bytes())
        results[path.name] = summary
        assert content.startswith("<?xml")
        assert len(digest) == 64
        assert summary.actuator_count > 0
    assert set(results) == {"sample-biped.xml", "sample-quadruped.xml"}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"", "empty"),
        (b"\xff\xfe", "UTF-8"),
        (b"PK\x03\x04archive", "archives"),
        (b"<!DOCTYPE mujoco><mujoco/>", "DTD"),
        (b'<!ENTITY x "boom"><mujoco/>', "entity"),
        (b"<mujoco>", "well-formed"),
        (b'<mujoco xmlns="urn:other"/>', "without a namespace"),
        (_robot(inner='<include file="other.xml"/>'), "<include>"),
        (_robot(inner='<plugin name="code"/>'), "<plugin>"),
        (_robot(inner='<texture name="pixels"/>'), "<texture>"),
        (_robot(inner='<hfield name="terrain"/>'), "<hfield>"),
        (_robot(inner='<geom name="mesh_geom" type="mesh"/>'), "geometry type"),
        (
            _robot(inner='<geom name="bad" type="box" mesh="outside"/>'),
            "attribute 'mesh'",
        ),
        (
            _robot(inner='<site name="bad" src="https://example.test/x"/>'),
            "attribute 'src'",
        ),
        (_robot(inner='<camera name="unsupported"/>'), "outside the supported"),
        (_robot(inner='<joint name="hinge" type="hinge"/>'), "duplicate joint"),
        (_robot(actuator='<motor name="motor" joint="missing"/>'), "unknown joint"),
        (_robot(actuator='<motor name="motor"/>'), "must reference"),
    ],
)
def test_hostile_or_unsupported_content_is_safely_rejected(raw: bytes, message: str):
    with pytest.raises(RobotValidationError, match=message):
        validate_mjcf(raw)


def test_size_body_joint_actuator_geom_and_depth_limits():
    with pytest.raises(RobotValidationError, match="1 MiB"):
        validate_mjcf(b" " * (MAX_ROBOT_BYTES + 1))

    bodies = "".join(f'<body name="child_{i}"/>' for i in range(64))
    with pytest.raises(RobotValidationError, match="body limit is 64"):
        validate_mjcf(_robot(inner=bodies))

    joints = "".join(f'<joint name="extra_{i}"/>' for i in range(63))
    with pytest.raises(RobotValidationError, match="joint limit is 64"):
        validate_mjcf(_robot(inner=joints))

    geoms = "".join(f'<geom name="extra_geom_{i}" type="sphere"/>' for i in range(128))
    with pytest.raises(RobotValidationError, match="geom limit is 128"):
        validate_mjcf(_robot(inner=geoms))

    actuators = "".join(
        f'<motor name="extra_motor_{i}" joint="hinge"/>' for i in range(65)
    )
    with pytest.raises(RobotValidationError, match="actuator limit is 64"):
        validate_mjcf(_robot(actuator=actuators))

    nested = (
        '<body name="deep_0">'
        + "".join(f'<body name="deep_{i}">' for i in range(1, 15))
        + "</body>" * 15
    )
    with pytest.raises(RobotValidationError, match="depth limit is 16"):
        validate_mjcf(_robot(inner=nested))


def test_summary_is_deterministic_and_normalized():
    raw = _robot(
        inner='<body name="leg"><joint name="ankle"/><geom name="leg_geom" type="capsule"/></body>',
        actuator='<motor name="z_motor" joint="hinge"/><motor name="a_motor" joint="ankle"/>',
    )
    first = validate_mjcf(raw)
    second = validate_mjcf(raw)
    assert first[1:] == second[1:]
    assert first[2].joint_names == ["ankle", "free", "hinge"]
    assert first[2].actuator_names == ["a_motor", "z_motor"]
