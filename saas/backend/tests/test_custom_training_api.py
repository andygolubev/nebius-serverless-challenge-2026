from __future__ import annotations

import time
import uuid
from dataclasses import replace

from app import main


def _email() -> str:
    return f"custom-{uuid.uuid4().hex[:10]}@nebius.com"


def _enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "_custom_settings",
        replace(
            main._custom_settings,
            enabled=True,
            runtime_image="local-custom-robot-sb3-v1",
            max_active_preparations_per_tenant=1,
            max_active_training_jobs_per_tenant=1,
            max_daily_starts_per_tenant=8,
        ),
    )
    monkeypatch.setattr(main._backend, "step_delay", 0.005)


def _setup(client, headers, *, objects: list[dict] | None = None) -> tuple[dict, dict]:
    sample = client.get("/robot-samples/sample-biped", headers=headers).content
    robot = client.post(
        "/robots",
        data={"name": "Training biped", "robot_type": "biped"},
        files={"file": ("training-biped.xml", sample, "application/xml")},
        headers=headers,
    ).json()
    setup = client.post(
        "/robot-setups",
        json={
            "name": "Balance setup",
            "robot_id": robot["id"],
            "task_template_id": "stand-balance",
            "scene_preset_id": "flat-arena",
            "objects": objects or [],
        },
        headers=headers,
    ).json()
    return robot, setup


def _wait_for(client, url: str, headers: dict[str, str], state: str) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get(url, headers=headers)
        if response.status_code == 200 and response.json()["state"] == state:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"did not observe {state}")


def test_prepare_ready_start_and_normal_job_flow(client, login, monkeypatch) -> None:
    _enabled(monkeypatch)
    headers = login(_email())
    robot, setup = _setup(client, headers)
    assert setup["training_readiness"] == "not_prepared"
    assert setup["can_prepare"] is True
    assert setup["can_start_training"] is False

    created = client.post(
        f"/robot-setups/{setup['id']}/preparations", json={}, headers=headers
    )
    assert created.status_code == 201
    preparation = created.json()
    duplicate = client.post(
        f"/robot-setups/{setup['id']}/preparations", json={}, headers=headers
    )
    assert duplicate.json()["id"] == preparation["id"]
    assert "input_manifest_key" not in preparation
    assert "report_key" not in preparation
    assert "nebius_job_id" not in preparation

    accepted = _wait_for(
        client,
        f"/robot-setups/{setup['id']}/preparations/latest",
        headers,
        "accepted",
    )
    assert accepted["report_ready"] is True
    ready = client.get(f"/robot-setups/{setup['id']}", headers=headers).json()
    assert ready["training_readiness"] == "ready"
    assert ready["can_start_training"] is True

    body = {"idempotency_key": "start-request-0001"}
    started = client.post(
        f"/robot-setups/{setup['id']}/training-jobs", json=body, headers=headers
    )
    assert started.status_code == 201
    job = started.json()
    assert job["job_kind"] == "custom-robot"
    assert job["algorithm"] == "ppo-sb3"
    assert job["preparation_id"] == preparation["id"]
    repeated = client.post(
        f"/robot-setups/{setup['id']}/training-jobs", json=body, headers=headers
    )
    assert repeated.json()["id"] == job["id"]
    assert client.get(f"/jobs/{job['id']}", headers=headers).status_code == 200
    projected = client.get(f"/robot-setups/{setup['id']}", headers=headers).json()
    assert projected["latest_training_job"]["id"] == job["id"]
    assert projected["latest_training_job"]["status"] in {
        "queued", "starting", "training", "finalizing", "rendering",
        "evaluating", "completed",
    }
    assert robot["id"] not in str(client.get("/training-options").json())


def test_optional_objects_are_eligible_and_unknown_fields_cross_tenant_are_bounded(
    client, login, monkeypatch
) -> None:
    _enabled(monkeypatch)
    owner = login(_email())
    stranger = login(_email())
    _, eligible = _setup(client, owner)
    _, with_object = _setup(
        client,
        owner,
        objects=[{"object_type": "box", "x": 2.0}],
    )
    assert with_object["training_readiness"] == "not_prepared"
    assert with_object["reason"] == "not-prepared"
    response = client.post(
        f"/robot-setups/{with_object['id']}/preparations", json={}, headers=owner
    )
    assert response.status_code == 201
    assert (
        client.post(
            f"/robot-setups/{eligible['id']}/preparations",
            json={"command": "python evil.py"},
            headers=owner,
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/robot-setups/{eligible['id']}/preparations/latest",
            headers=stranger,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/robot-setups/{eligible['id']}/training-jobs",
            json={"idempotency_key": "../../unsafe"},
            headers=owner,
        ).status_code
        == 422
    )


def test_stale_fingerprint_and_deleted_sources_block_new_starts(
    client, login, monkeypatch
) -> None:
    _enabled(monkeypatch)
    headers = login(_email())
    robot, setup = _setup(client, headers)
    client.post(f"/robot-setups/{setup['id']}/preparations", json={}, headers=headers)
    _wait_for(
        client,
        f"/robot-setups/{setup['id']}/preparations/latest",
        headers,
        "accepted",
    )
    monkeypatch.setattr(
        main,
        "_custom_settings",
        replace(main._custom_settings, runtime_image="local-custom-robot-sb3-v2"),
    )
    stale = client.get(f"/robot-setups/{setup['id']}", headers=headers).json()
    assert stale["training_readiness"] == "not_prepared"
    assert (
        client.post(
            f"/robot-setups/{setup['id']}/training-jobs",
            json={"idempotency_key": "stale-start-0001"},
            headers=headers,
        ).status_code
        == 409
    )
    assert client.delete(f"/robots/{robot['id']}", headers=headers).status_code == 204
    assert (
        client.post(
            f"/robot-setups/{setup['id']}/preparations", json={}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.get(
            f"/robot-setups/{setup['id']}/preparations/latest", headers=headers
        ).status_code
        == 200
    )


def test_failed_preparation_exposes_retry_and_creates_new_attempt(
    client, login, monkeypatch
) -> None:
    _enabled(monkeypatch)
    headers = login(_email())
    _, setup = _setup(client, headers)

    def fail_preparation(attempt, store) -> None:
        store.put_preparation(
            attempt.model_copy(
                update={
                    "state": "failed",
                    "phase": "render",
                    "failure_phase": "render",
                    "failure_reason": "render-probe-failed",
                    "can_retry": True,
                }
            )
        )

    monkeypatch.setattr(main._backend, "launch_preparation", fail_preparation)
    first = client.post(
        f"/robot-setups/{setup['id']}/preparations", json={}, headers=headers
    ).json()
    failed = client.get(f"/robot-setups/{setup['id']}", headers=headers).json()
    assert failed["training_readiness"] == "preparation_failed"
    assert failed["current_preparation"]["can_retry"] is True
    assert failed["current_preparation"]["failure_reason"] == "render-probe-failed"

    retry_response = client.post(
        f"/robot-setups/{setup['id']}/preparations",
        json={"retry": True},
        headers=headers,
    )
    assert retry_response.status_code == 201
    retry = retry_response.json()
    assert retry["id"] != first["id"]
    assert retry["retry_of"] == first["id"]


def test_active_preparation_quota_is_atomic(
    client, login, monkeypatch
) -> None:
    _enabled(monkeypatch)
    headers = login(_email())
    robot, first_setup = _setup(client, headers)
    second_setup = client.post(
        "/robot-setups",
        json={
            "name": "Ramp setup",
            "robot_id": robot["id"],
            "task_template_id": "stand-balance",
            "scene_preset_id": "ramp-course",
            "objects": [],
        },
        headers=headers,
    ).json()

    monkeypatch.setattr(main._backend, "launch_preparation", lambda *_args: None)
    assert (
        client.post(
            f"/robot-setups/{first_setup['id']}/preparations",
            json={},
            headers=headers,
        ).status_code
        == 201
    )
    blocked = client.post(
        f"/robot-setups/{second_setup['id']}/preparations",
        json={},
        headers=headers,
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["reason"] == "active_preparations"


def test_daily_training_start_quota_counts_completed_custom_jobs(
    client, login, monkeypatch
) -> None:
    _enabled(monkeypatch)
    monkeypatch.setattr(
        main,
        "_custom_settings",
        replace(
            main._custom_settings,
            max_active_preparations_per_tenant=10,
            max_active_training_jobs_per_tenant=10,
            max_daily_starts_per_tenant=1,
        ),
    )
    headers = login(_email())
    robot, first_setup = _setup(client, headers)
    second_setup = client.post(
        "/robot-setups",
        json={
            "name": "Second trainable setup",
            "robot_id": robot["id"],
            "task_template_id": "walk-forward",
            "scene_preset_id": "flat-arena",
            "objects": [],
        },
        headers=headers,
    ).json()
    for setup in (first_setup, second_setup):
        client.post(
            f"/robot-setups/{setup['id']}/preparations", json={}, headers=headers
        )
        _wait_for(
            client,
            f"/robot-setups/{setup['id']}/preparations/latest",
            headers,
            "accepted",
        )
    first = client.post(
        f"/robot-setups/{first_setup['id']}/training-jobs",
        json={"idempotency_key": "daily-start-first"},
        headers=headers,
    )
    assert first.status_code == 201
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if client.get(f"/jobs/{first.json()['id']}", headers=headers).json()["status"] == "completed":
            break
        time.sleep(0.01)
    second = client.post(
        f"/robot-setups/{second_setup['id']}/training-jobs",
        json={"idempotency_key": "daily-start-second"},
        headers=headers,
    )
    assert second.status_code == 429
    assert second.json()["detail"]["reason"] == "daily_training_starts"


def test_deleted_setup_keeps_started_job_and_preparation_history(
    client, login, monkeypatch
) -> None:
    _enabled(monkeypatch)
    headers = login(_email())
    _, setup = _setup(client, headers)
    client.post(f"/robot-setups/{setup['id']}/preparations", json={}, headers=headers)
    preparation = _wait_for(
        client,
        f"/robot-setups/{setup['id']}/preparations/latest",
        headers,
        "accepted",
    )
    job = client.post(
        f"/robot-setups/{setup['id']}/training-jobs",
        json={"idempotency_key": "retained-job-start"},
        headers=headers,
    ).json()

    assert client.delete(f"/robot-setups/{setup['id']}", headers=headers).status_code == 204
    assert client.get(f"/robot-setups/{setup['id']}", headers=headers).status_code == 404
    assert (
        client.post(
            f"/robot-setups/{setup['id']}/training-jobs",
            json={"idempotency_key": "blocked-after-delete"},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/robot-setups/{setup['id']}/preparations/latest", headers=headers
        ).json()["id"]
        == preparation["id"]
    )
    assert client.get(f"/jobs/{job['id']}", headers=headers).status_code == 200
