"""Job submission: the catalog path is gone; only an owned robot setup creates jobs."""

from __future__ import annotations

import uuid

import pytest


def _email() -> str:
    return f"{uuid.uuid4().hex[:10]}@nebius.com"


def test_training_options_is_showcase_display_metadata(client):
    res = client.get("/training-options")
    assert res.status_code == 200
    data = res.json()
    # Display metadata only: no submittable environment, algorithm, preset, profile,
    # or parameter contract may be advertised, because nothing accepts one.
    assert set(data) == {"showcase_enabled", "examples"}
    for absent in ("environments", "algorithms", "presets", "optional_params"):
        assert absent not in data


def test_training_options_needs_no_session(client):
    assert client.get("/training-options").status_code == 200


# Every shape the old catalog composer could submit. None may create a job.
REFUSED_PAYLOADS = [
    pytest.param({"gallery_example_id": "hopper-balance"}, id="gallery-example"),
    pytest.param(
        {"gallery_example_id": "go1-walker", "gallery_profile_id": "go1-mjx-quality"},
        id="gallery-profile",
    ),
    pytest.param({"preset": "go1-mjx-quick"}, id="go1-preset-quick"),
    pytest.param({"preset": "go1-mjx-standard"}, id="go1-preset-standard"),
    pytest.param({"preset": "go1-mjx-quality"}, id="go1-preset-quality"),
    pytest.param({"environment": "go1", "algorithm": "ppo-mjx"}, id="raw-env-algorithm"),
    pytest.param(
        {"environment": "go1", "algorithm": "ppo-mjx", "params": {"total_timesteps": 5_000_000}},
        id="raw-with-params",
    ),
    pytest.param({"params": {"docker_image": "evil"}}, id="arbitrary-param"),
    pytest.param({}, id="empty"),
]


@pytest.mark.parametrize("payload", REFUSED_PAYLOADS)
def test_post_jobs_refuses_every_catalog_payload(client, sender, login, payload):
    headers = login(_email())
    before = len(client.get("/jobs", headers=headers).json())

    res = client.post("/jobs", json=payload, headers=headers)
    assert res.status_code == 410
    detail = res.json()["detail"]
    # The refusal names the supported path rather than just saying no.
    assert "read-only showcase" in detail["message"]
    assert "/robot-setups/" in detail["message"]

    # No SaaS job record was created by any of it.
    assert len(client.get("/jobs", headers=headers).json()) == before


def test_post_jobs_still_requires_a_session(client):
    # The refusal must not become an unauthenticated information leak.
    assert client.post("/jobs", json={"preset": "go1-mjx-quick"}).status_code == 401


def test_only_the_custom_setup_route_creates_jobs():
    """The service exposes exactly one job-creating endpoint."""
    from app.main import app

    creating = {
        f"{method} {route.path}"
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method == "POST" and "training-jobs" in route.path
    }
    assert creating == {"POST /robot-setups/{setup_id}/training-jobs"}

    # And no route advertises a catalog job creation contract.
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/jobs" in paths  # retained, but only to refuse
    assert not any("gallery" in path for path in paths)
