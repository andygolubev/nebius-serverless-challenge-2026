"""Authenticated sample and immutable robot API behavior."""

from __future__ import annotations

import uuid


def _email() -> str:
    return f"robot-{uuid.uuid4().hex[:10]}@nebius.com"


def test_sample_routes_require_auth_and_samples_round_trip_through_upload(
    client, login
):
    assert client.get("/robot-samples").status_code == 401
    headers = login(_email())
    response = client.get("/robot-samples", headers=headers)
    assert response.status_code == 200
    samples = response.json()
    assert {(sample["id"], sample["robot_type"]) for sample in samples} == {
        ("sample-quadruped", "quadruped"),
        ("sample-biped", "biped"),
    }
    for sample in samples:
        download = client.get(f"/robot-samples/{sample['id']}", headers=headers)
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/xml")
        uploaded = client.post(
            "/robots",
            data={"name": sample["name"], "robot_type": sample["robot_type"]},
            files={"file": (sample["filename"], download.content, "application/xml")},
            headers=headers,
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["digest"] == sample["digest"]
        assert uploaded.json()["readiness"] == "validated"
        assert uploaded.json()["trainable"] is False
        assert uploaded.json()["reason"] == "custom-training-not-enabled"
        assert "tenant_id" not in uploaded.json()


def test_robot_upload_list_detail_content_idempotency_and_soft_delete(client, login):
    headers = login(_email())
    sample = client.get("/robot-samples/sample-quadruped", headers=headers).content
    files = {"file": ("my-robot.xml", sample, "application/xml")}
    first = client.post(
        "/robots",
        data={"name": "Warehouse walker", "robot_type": "quadruped"},
        files=files,
        headers=headers,
    )
    assert first.status_code == 201
    robot = first.json()
    duplicate = client.post(
        "/robots",
        data={"name": "Renamed retry", "robot_type": "quadruped"},
        files={"file": ("retry.xml", sample, "application/xml")},
        headers=headers,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == robot["id"]
    assert duplicate.json()["name"] == "Warehouse walker"
    assert [item["id"] for item in client.get("/robots", headers=headers).json()] == [
        robot["id"]
    ]
    assert client.get(f"/robots/{robot['id']}", headers=headers).json() == robot
    content = client.get(f"/robots/{robot['id']}/content", headers=headers)
    assert content.content == sample
    assert "my-robot.xml" in content.headers["content-disposition"]
    assert client.delete(f"/robots/{robot['id']}", headers=headers).status_code == 204
    assert client.get(f"/robots/{robot['id']}", headers=headers).status_code == 404
    assert (
        client.get(f"/robots/{robot['id']}/content", headers=headers).status_code == 404
    )
    assert client.get("/robots", headers=headers).json() == []


def test_robot_routes_hide_other_tenants(client, login):
    owner = login(_email())
    stranger = login(_email())
    sample = client.get("/robot-samples/sample-biped", headers=owner).content
    created = client.post(
        "/robots",
        data={"name": "Private biped", "robot_type": "biped"},
        files={"file": ("private.xml", sample, "application/xml")},
        headers=owner,
    ).json()
    for method, suffix in [("get", ""), ("get", "/content"), ("delete", "")]:
        response = getattr(client, method)(
            f"/robots/{created['id']}{suffix}", headers=stranger
        )
        assert response.status_code == 404
    assert client.get(f"/robots/{created['id']}", headers=owner).status_code == 200


def test_robot_upload_errors_are_bounded_sanitized_and_non_persistent(client, login):
    headers = login(_email())
    cases = [
        (
            {"name": "", "robot_type": "quadruped"},
            ("robot.xml", b"<mujoco/>", "application/xml"),
            "name",
        ),
        (
            {"name": "Robot", "robot_type": "snake"},
            ("robot.xml", b"<mujoco/>", "application/xml"),
            "robot_type",
        ),
        (
            {"name": "Robot", "robot_type": "quadruped"},
            ("../robot.xml", b"<mujoco/>", "application/xml"),
            "file",
        ),
        (
            {"name": "Robot", "robot_type": "quadruped"},
            ('bad"name.xml', b"<mujoco/>", "application/xml"),
            "file",
        ),
        (
            {"name": "Robot", "robot_type": "quadruped"},
            ("robot.xml", b"<!DOCTYPE x><mujoco/>", "application/xml"),
            "file",
        ),
        (
            {"name": "Robot", "robot_type": "quadruped"},
            ("robot.xml", b"secret-raw-content", "application/xml"),
            "file",
        ),
    ]
    for data, file, field in cases:
        response = client.post(
            "/robots", data=data, files={"file": file}, headers=headers
        )
        assert response.status_code == 422
        assert response.json()["detail"]["field"] == field
        assert "secret-raw-content" not in response.text
    missing_file = client.post(
        "/robots",
        data={"name": "Robot", "robot_type": "quadruped"},
        headers=headers,
    )
    assert missing_file.status_code == 422
    assert missing_file.json()["detail"]["field"] == "file"
    assert client.get("/robots", headers=headers).json() == []
