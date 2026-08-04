"""Server-owned setup catalog, normalization, compatibility, and training isolation."""

from __future__ import annotations

import uuid

import pytest


def _email() -> str:
    return f"setup-{uuid.uuid4().hex[:10]}@nebius.com"


def _upload_sample(client, headers, sample_id: str, robot_type: str) -> dict:
    raw = client.get(f"/robot-samples/{sample_id}", headers=headers).content
    response = client.post(
        "/robots",
        data={"name": f"My {robot_type}", "robot_type": robot_type},
        files={"file": (f"{robot_type}.xml", raw, "application/xml")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_environment_catalog_has_exact_bounded_server_owned_choices(client, login):
    headers = login(_email())
    response = client.get("/environment-catalog", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert [task["id"] for task in data["task_templates"]] == [
        "stand-balance",
        "walk-forward",
        "recover-from-fall",
    ]
    assert [scene["id"] for scene in data["scene_presets"]] == [
        "flat-arena",
        "ramp-course",
        "hurdle-course",
        "step-course",
    ]
    assert [object_["id"] for object_ in data["object_types"]] == [
        "box",
        "ramp",
        "hurdle",
        "step",
    ]
    assert data["max_objects"] == 6
    for object_ in data["object_types"]:
        assert all(
            {"default", "minimum", "maximum"} <= set(param)
            for param in object_["parameters"]
        )


def test_valid_setup_resolves_defaults_persists_and_is_idempotent(client, login):
    headers = login(_email())
    robot = _upload_sample(client, headers, "sample-quadruped", "quadruped")
    body = {
        "name": "Delivery course",
        "robot_id": robot["id"],
        "task_template_id": "walk-forward",
        "scene_preset_id": "ramp-course",
        "objects": [{"object_type": "box", "x": 7, "height": 0.2}],
    }
    created = client.post("/robot-setups", json=body, headers=headers)
    assert created.status_code == 201
    setup = created.json()
    assert setup["readiness"] == "validated"
    assert setup["trainable"] is False
    assert setup["reason"] == "custom-training-not-enabled"
    assert len(setup["objects"]) == 2
    assert setup["objects"][0]["source"] == "preset"
    assert setup["objects"][1] == {
        "object_type": "box",
        "x": 7.0,
        "y": 0.0,
        "z": 0.0,
        "yaw_degrees": 0.0,
        "width": 1.0,
        "depth": 1.0,
        "height": 0.2,
        "source": "custom",
    }
    retry = client.post(
        "/robot-setups", json={**body, "name": "Retry"}, headers=headers
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == setup["id"]
    assert client.get("/robot-setups", headers=headers).json() == [setup]
    assert client.get(f"/robot-setups/{setup['id']}", headers=headers).json() == setup


@pytest.mark.parametrize(
    ("sample_id", "robot_type", "task_id", "expected"),
    [
        ("sample-quadruped", "quadruped", "stand-balance", 201),
        ("sample-quadruped", "quadruped", "walk-forward", 201),
        ("sample-quadruped", "quadruped", "recover-from-fall", 201),
        ("sample-biped", "biped", "stand-balance", 201),
        ("sample-biped", "biped", "walk-forward", 201),
        ("sample-biped", "biped", "recover-from-fall", 422),
    ],
)
def test_every_task_compatibility_rule(
    client, login, sample_id, robot_type, task_id, expected
):
    headers = login(_email())
    robot = _upload_sample(client, headers, sample_id, robot_type)
    response = client.post(
        "/robot-setups",
        json={
            "name": "Compatibility check",
            "robot_id": robot["id"],
            "task_template_id": task_id,
            "scene_preset_id": "flat-arena",
        },
        headers=headers,
    )
    assert response.status_code == expected


@pytest.mark.parametrize(
    ("scene_id", "preset_objects"),
    [("flat-arena", 0), ("ramp-course", 1), ("hurdle-course", 3), ("step-course", 3)],
)
def test_every_scene_preset_resolves_to_normalized_objects(
    client, login, scene_id, preset_objects
):
    headers = login(_email())
    robot = _upload_sample(client, headers, "sample-quadruped", "quadruped")
    response = client.post(
        "/robot-setups",
        json={
            "name": scene_id,
            "robot_id": robot["id"],
            "task_template_id": "walk-forward",
            "scene_preset_id": scene_id,
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert len(response.json()["objects"]) == preset_objects
    assert all(object_["source"] == "preset" for object_ in response.json()["objects"])


def test_builder_rejects_incompatible_excessive_out_of_bounds_and_file_like_fields(
    client, login
):
    headers = login(_email())
    biped = _upload_sample(client, headers, "sample-biped", "biped")
    base = {
        "name": "Biped setup",
        "robot_id": biped["id"],
        "task_template_id": "walk-forward",
        "scene_preset_id": "flat-arena",
        "objects": [],
    }
    cases = [
        ({**base, "task_template_id": "recover-from-fall"}, "task_template_id"),
        ({**base, "objects": [{"object_type": "box"}] * 7}, "objects"),
        ({**base, "objects": [{"object_type": "ramp", "x": 11}]}, "objects.0"),
    ]
    for body, field in cases:
        response = client.post("/robot-setups", json=body, headers=headers)
        assert response.status_code == 422
        assert response.json()["detail"]["field"] == field
    for forbidden in ["object_file", "environment_url", "task_code"]:
        response = client.post(
            "/robot-setups",
            json={**base, forbidden: "https://evil.test"},
            headers=headers,
        )
        assert response.status_code == 422
    for objects in [
        [{"object_type": "pyramid"}],
        [{"object_type": "box", "height": 3}],
        [{"object_type": "box", "mesh_url": "https://evil.test/object.obj"}],
    ]:
        response = client.post(
            "/robot-setups", json={**base, "objects": objects}, headers=headers
        )
        assert response.status_code == 422
    assert client.get("/robot-setups", headers=headers).json() == []


def test_setup_routes_hide_other_tenants_and_soft_delete(client, login):
    owner = login(_email())
    stranger = login(_email())
    robot = _upload_sample(client, owner, "sample-quadruped", "quadruped")
    foreign_reference = client.post(
        "/robot-setups",
        json={
            "name": "No",
            "robot_id": robot["id"],
            "task_template_id": "walk-forward",
            "scene_preset_id": "flat-arena",
        },
        headers=stranger,
    )
    assert foreign_reference.status_code == 404
    setup = client.post(
        "/robot-setups",
        json={
            "name": "Owned",
            "robot_id": robot["id"],
            "task_template_id": "walk-forward",
            "scene_preset_id": "flat-arena",
        },
        headers=owner,
    ).json()
    assert (
        client.get(f"/robot-setups/{setup['id']}", headers=stranger).status_code == 404
    )
    assert (
        client.delete(f"/robot-setups/{setup['id']}", headers=stranger).status_code
        == 404
    )
    assert (
        client.delete(f"/robot-setups/{setup['id']}", headers=owner).status_code == 204
    )
    assert client.get(f"/robot-setups/{setup['id']}", headers=owner).status_code == 404


def test_custom_robots_and_setups_never_enter_training_catalog_or_jobs(client, login):
    headers = login(_email())
    robot = _upload_sample(client, headers, "sample-quadruped", "quadruped")
    setup = client.post(
        "/robot-setups",
        json={
            "name": "Not trainable",
            "robot_id": robot["id"],
            "task_template_id": "walk-forward",
            "scene_preset_id": "flat-arena",
        },
        headers=headers,
    ).json()
    options = client.get("/training-options").json()
    # The showcase publishes evidence only; it names no custom asset and no
    # submittable environment.
    assert "environments" not in options
    assert robot["id"] not in str(options)
    assert setup["id"] not in str(options)
    # And `POST /jobs` refuses every payload, custom identifiers included: 410 from
    # the handler, or 422 when the schema rejects an undeclared field even earlier.
    before = len(client.get("/jobs", headers=headers).json())
    for payload in ({"robot_id": robot["id"]}, {"setup_id": setup["id"]}):
        assert client.post("/jobs", json=payload, headers=headers).status_code in {410, 422}
    assert len(client.get("/jobs", headers=headers).json()) == before
