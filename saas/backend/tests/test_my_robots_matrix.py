"""Exhaustive cheap-layer matrix for every My Robots catalog choice and bound."""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from dataclasses import replace

import pytest

from app import main
from validation_suite.matrix import (
    CONTROL_INVENTORY,
    EXPECTED_COMPATIBILITY,
    EXPECTED_ELIGIBLE_SCENES,
    EXPECTED_ELIGIBLE_TASKS,
    EXPECTED_OBJECT_TYPES,
    EXPECTED_PARAMETER_NAMES,
    EXPECTED_ROBOT_TYPES,
    capacity_cases,
    expected_case_ids,
    object_parameter_cases,
    positive_setup_cases,
    select_shard,
)

SHARD_TOTAL = int(os.environ.get("FORM_MATRIX_SHARD_TOTAL", "1"))
SHARD_INDEX = int(os.environ.get("FORM_MATRIX_SHARD_INDEX", "0"))
SETUP_CASES = select_shard(
    positive_setup_cases(), index=SHARD_INDEX, total=SHARD_TOTAL
)
PARAMETER_CASES = select_shard(
    object_parameter_cases(), index=SHARD_INDEX, total=SHARD_TOTAL
)
CAPACITY_CASES = select_shard(
    capacity_cases(), index=SHARD_INDEX, total=SHARD_TOTAL
)


def _email(prefix: str = "matrix") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@nebius.com"


def _enable_training(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "_custom_settings",
        replace(
            main._custom_settings,
            enabled=True,
            runtime_image="local-custom-robot-sb3-v1",
            max_active_preparations_per_tenant=2,
            max_active_training_jobs_per_tenant=2,
            max_daily_starts_per_tenant=20,
        ),
    )


def _sample_bytes(client, headers, robot_type: str) -> bytes:
    sample_id = "sample-quadruped" if robot_type == "quadruped" else "sample-biped"
    response = client.get(f"/robot-samples/{sample_id}", headers=headers)
    assert response.status_code == 200
    return response.content


def _upload(client, headers, robot_type: str, *, name: str | None = None) -> dict:
    response = client.post(
        "/robots",
        data={"name": name or f"Matrix {robot_type}", "robot_type": robot_type},
        files={
            "file": (
                f"matrix-{robot_type}.xml",
                _sample_bytes(client, headers, robot_type),
                "application/xml",
            )
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    ("sample_id", "declared_type"),
    [
        (sample_id, declared_type)
        for sample_id in ("sample-quadruped", "sample-biped")
        for declared_type in EXPECTED_ROBOT_TYPES
    ],
    ids=lambda value: value,
)
def test_upload_sample_through_every_declared_type_path(
    client, login, sample_id: str, declared_type: str
) -> None:
    """Case IDs: api:upload:<sample-id>:<declared-type>."""
    owner = login(_email("upload-owner"))
    stranger = login(_email("upload-stranger"))
    sample = client.get(f"/robot-samples/{sample_id}", headers=owner)
    metadata = {
        item["id"]: item
        for item in client.get("/robot-samples", headers=owner).json()
    }[sample_id]
    assert sample.status_code == 200
    response = client.post(
        "/robots",
        data={"name": "Declared type path", "robot_type": declared_type},
        files={"file": (metadata["filename"], sample.content, "application/xml")},
        headers=owner,
    )
    assert response.status_code == 201
    robot = response.json()
    assert robot["robot_type"] == declared_type
    assert robot["digest"] == metadata["digest"]
    assert robot["validation"] == metadata["validation"]

    duplicate = client.post(
        "/robots",
        data={"name": "Ignored duplicate name", "robot_type": declared_type},
        files={"file": (metadata["filename"], sample.content, "application/xml")},
        headers=owner,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == robot["id"]
    downloaded = client.get(f"/robots/{robot['id']}/content", headers=owner)
    assert downloaded.content == sample.content
    assert client.get(f"/robots/{robot['id']}", headers=stranger).status_code == 404
    assert (
        client.get(f"/robots/{robot['id']}/content", headers=stranger).status_code
        == 404
    )

    # Task filtering follows the declared type; the upload contract deliberately does
    # not infer morphology from the XML sample.
    recover = client.post(
        "/robot-setups",
        json={
            "name": "Declared type filtering",
            "robot_id": robot["id"],
            "task_template_id": "recover-from-fall",
            "scene_preset_id": "flat-arena",
            "objects": [],
        },
        headers=owner,
    )
    assert recover.status_code == (201 if declared_type == "quadruped" else 422)
    assert client.delete(f"/robots/{robot['id']}", headers=owner).status_code == 204
    assert client.get(f"/robots/{robot['id']}", headers=owner).status_code == 404


def test_upload_diagnostics_and_active_quota_are_bounded(client, login) -> None:
    headers = login(_email("upload-quota"))
    for data, files, expected_field in (
        ({"name": "", "robot_type": "biped"}, {}, "name"),
        ({"name": "Missing file", "robot_type": "biped"}, {}, "file"),
        (
            {"name": "Wrong type", "robot_type": "wheeled"},
            {"file": ("robot.xml", b"<mujoco/>", "application/xml")},
            "robot_type",
        ),
        (
            {"name": "Unsafe name", "robot_type": "biped"},
            {"file": ("../robot.xml", b"<mujoco/>", "application/xml")},
            "file",
        ),
    ):
        response = client.post("/robots", data=data, files=files, headers=headers)
        assert response.status_code == 422
        assert response.json()["detail"]["field"] == expected_field

    sample = _sample_bytes(client, headers, "biped")
    created: list[str] = []
    for index in range(20):
        unique = re.sub(
            rb'(<mujoco\s+model=")[^"]+',
            rf"\g<1>quota-{index}".encode(),
            sample,
            count=1,
        )
        response = client.post(
            "/robots",
            data={"name": f"Quota {index}", "robot_type": "biped"},
            files={"file": (f"quota-{index}.xml", unique, "application/xml")},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        created.append(response.json()["id"])
    overflow = re.sub(
        rb'(<mujoco\s+model=")[^"]+',
        rb"\g<1>quota-overflow",
        sample,
        count=1,
    )
    response = client.post(
        "/robots",
        data={"name": "Quota overflow", "robot_type": "biped"},
        files={"file": ("quota-overflow.xml", overflow, "application/xml")},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "robots"
    for robot_id in created:
        assert client.delete(f"/robots/{robot_id}", headers=headers).status_code == 204


@pytest.mark.parametrize("case", SETUP_CASES, ids=lambda case: case.case_id)
def test_every_positive_setup_combination(client, login, monkeypatch, case) -> None:
    _enable_training(monkeypatch)
    headers = login(_email("setup-matrix"))
    robot = _upload(client, headers, case.robot_type)
    objects = [] if case.object_type is None else [{"object_type": case.object_type}]
    body = {
        "name": case.case_id[-80:],
        "robot_id": robot["id"],
        "task_template_id": case.task_id,
        "scene_preset_id": case.scene_id,
        "objects": objects,
    }
    response = client.post("/robot-setups", json=body, headers=headers)
    assert response.status_code == 201, response.text
    setup = response.json()
    preset_count = {
        "flat-arena": 0,
        "ramp-course": 1,
        "hurdle-course": 3,
        "step-course": 3,
    }[case.scene_id]
    assert len(setup["objects"]) == preset_count + len(objects)
    assert setup["reason"] == case.expected_reason
    assert setup["training_readiness"] == (
        "not_prepared" if case.expected_reason == "not-prepared" else "ineligible"
    )
    assert setup["can_prepare"] is (case.expected_reason == "not-prepared")
    assert setup["can_start_training"] is False
    duplicate = client.post(
        "/robot-setups", json={**body, "name": "Idempotent rename"}, headers=headers
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == setup["id"]
    assert duplicate.json()["digest"] == setup["digest"]


@pytest.mark.parametrize("case", PARAMETER_CASES, ids=lambda case: case.case_id)
def test_every_object_parameter_boundary(client, login, case) -> None:
    headers = login(_email("parameter-matrix"))
    robot = _upload(client, headers, "biped")
    response = client.post(
        "/robot-setups",
        json={
            "name": case.case_id[-80:],
            "robot_id": robot["id"],
            "task_template_id": "walk-forward",
            "scene_preset_id": "flat-arena",
            "objects": [
                {"object_type": case.object_type, case.parameter: case.value}
            ],
        },
        headers=headers,
    )
    if case.valid:
        assert response.status_code == 201, response.text
        custom = response.json()["objects"][-1]
        assert custom[case.parameter] == pytest.approx(case.value)
    else:
        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "objects.0"
        assert client.get("/robot-setups", headers=headers).json() == []


@pytest.mark.parametrize("literal", ("NaN", "Infinity", "-Infinity"))
def test_non_finite_object_parameter_is_rejected(client, login, literal: str) -> None:
    headers = login(_email("non-finite"))
    robot = _upload(client, headers, "biped")
    body = (
        '{"name":"Non finite","robot_id":'
        + json.dumps(robot["id"])
        + ',"task_template_id":"walk-forward","scene_preset_id":"flat-arena",'
        + f'"objects":[{{"object_type":"box","x":{literal}}}]}}'
    )
    response = client.post(
        "/robot-setups",
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "objects.0"
    assert client.get("/robot-setups", headers=headers).json() == []


@pytest.mark.parametrize("case", CAPACITY_CASES, ids=lambda case: case.case_id)
def test_every_scene_capacity_transition(client, login, case) -> None:
    headers = login(_email("capacity-matrix"))
    robot = _upload(client, headers, "quadruped")
    response = client.post(
        "/robot-setups",
        json={
            "name": case.case_id,
            "robot_id": robot["id"],
            "task_template_id": "walk-forward",
            "scene_preset_id": case.scene_id,
            "objects": [{"object_type": "box"}] * case.optional_count,
        },
        headers=headers,
    )
    if case.valid:
        assert response.status_code == 201, response.text
        assert len(response.json()["objects"]) == 6
    else:
        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "objects"
        assert client.get("/robot-setups", headers=headers).json() == []


def test_incompatible_unknown_and_cross_tenant_inputs_never_persist(client, login) -> None:
    owner = login(_email("matrix-owner"))
    stranger = login(_email("matrix-stranger"))
    robot = _upload(client, owner, "biped")
    base = {
        "name": "Rejected matrix input",
        "robot_id": robot["id"],
        "task_template_id": "walk-forward",
        "scene_preset_id": "flat-arena",
        "objects": [],
    }
    for body, expected_status, expected_field in (
        ({**base, "task_template_id": "recover-from-fall"}, 422, "task_template_id"),
        ({**base, "task_template_id": "unknown"}, 422, "task_template_id"),
        ({**base, "scene_preset_id": "unknown"}, 422, "scene_preset_id"),
        ({**base, "objects": [{"object_type": "pyramid"}]}, 422, None),
        ({**base, "environment_url": "https://invalid.example"}, 422, None),
        ({**base, "robot_id": robot["id"]}, 404, None),
    ):
        headers = stranger if expected_status == 404 else owner
        response = client.post("/robot-setups", json=body, headers=headers)
        assert response.status_code == expected_status
        if expected_field is not None:
            assert response.json()["detail"]["field"] == expected_field
    assert client.get("/robot-setups", headers=owner).json() == []
    assert client.get("/robot-setups", headers=stranger).json() == []


def test_matrix_contract_counts_controls_and_shards_are_complete() -> None:
    setups = positive_setup_cases()
    assert len(setups) == 100
    assert sum(case.object_type is None for case in setups) == 20
    assert sum(case.object_type is not None for case in setups) == 80
    assert sum(case.expected_reason == "not-prepared" for case in setups) == 8
    assert set(EXPECTED_COMPATIBILITY) == set(EXPECTED_ROBOT_TYPES)
    assert set(EXPECTED_ELIGIBLE_TASKS) == {"stand-balance", "walk-forward"}
    assert set(EXPECTED_ELIGIBLE_SCENES) == {"flat-arena", "ramp-course"}
    assert len(EXPECTED_OBJECT_TYPES) * len(EXPECTED_PARAMETER_NAMES) == 28
    assert len(CONTROL_INVENTORY) >= 32
    assert all(case_ids for case_ids in CONTROL_INVENTORY.values())
    assert len(expected_case_ids()) == len(set(expected_case_ids()))

    all_ids = {case.case_id for case in setups}
    shards = [
        {case.case_id for case in select_shard(setups, index=index, total=4)}
        for index in range(4)
    ]
    assert set().union(*shards) == all_ids
    assert all(left.isdisjoint(right) for i, left in enumerate(shards) for right in shards[i + 1 :])


def test_boundary_values_are_finite_and_directional() -> None:
    grouped: dict[tuple[str, str], dict[str, float]] = {}
    for case in object_parameter_cases():
        assert math.isfinite(case.value)
        grouped.setdefault((case.object_type, case.parameter), {})[case.variant] = case.value
    assert len(grouped) == 28
    for variants in grouped.values():
        assert variants["below"] < variants["minimum"] <= variants["default"]
        assert variants["default"] <= variants["maximum"] < variants["above"]
