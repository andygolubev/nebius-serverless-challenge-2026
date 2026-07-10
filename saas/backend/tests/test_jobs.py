"""Job customization: catalog-driven validation, presets, resolved config."""

from __future__ import annotations

import uuid


def _email() -> str:
    return f"{uuid.uuid4().hex[:10]}@example.com"


def test_training_options_catalog(client):
    res = client.get("/training-options")
    assert res.status_code == 200
    data = res.json()
    env_ids = {e["id"] for e in data["environments"]}
    assert {"halfcheetah", "ant", "go1"} <= env_ids
    algo = next(a for a in data["algorithms"] if a["id"] == "ppo-sb3")
    lr = next(p for p in algo["params"] if p["name"] == "learning_rate")
    assert {"type", "default", "min", "max"} <= set(lr)
    assert any(p["id"] == "ant-demo" for p in data["presets"])


def test_valid_custom_job(client, sender, login):
    headers = login(_email())
    res = client.post(
        "/jobs",
        json={"environment": "ant", "algorithm": "ppo-sb3", "params": {"learning_rate": 1e-3}},
        headers=headers,
    )
    assert res.status_code == 201
    job = res.json()
    assert job["environment"] == "ant"
    assert job["algorithm"] == "ppo-sb3"
    cfg = job["resolved_config"]
    assert cfg["params"]["learning_rate"] == 1e-3
    # Defaults are merged in and visible.
    assert cfg["params"]["total_timesteps"] == 100_000
    assert "seed" in cfg["params"]


def test_out_of_range_param_rejected(client, sender, login):
    headers = login(_email())
    res = client.post(
        "/jobs",
        json={"environment": "ant", "algorithm": "ppo-sb3", "params": {"total_timesteps": 10_000_000}},
        headers=headers,
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["field"] == "total_timesteps"
    assert "between" in detail["message"]


def test_unknown_environment_and_algorithm_rejected(client, sender, login):
    headers = login(_email())
    res = client.post("/jobs", json={"environment": "walker", "algorithm": "ppo-sb3"}, headers=headers)
    assert res.status_code == 422
    assert res.json()["detail"]["field"] == "environment"
    # go1 only supports ppo-mjx.
    res = client.post("/jobs", json={"environment": "go1", "algorithm": "ppo-sb3"}, headers=headers)
    assert res.status_code == 422
    assert res.json()["detail"]["field"] == "algorithm"


def test_unknown_param_rejected(client, sender, login):
    headers = login(_email())
    res = client.post(
        "/jobs",
        json={"environment": "ant", "algorithm": "ppo-sb3", "params": {"docker_image": "evil"}},
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["detail"]["field"] == "docker_image"


def test_preset_expansion(client, sender, login):
    headers = login(_email())
    res = client.post("/jobs", json={"preset": "ant-demo", "seed": 42}, headers=headers)
    assert res.status_code == 201
    job = res.json()
    assert job["preset"] == "ant-demo"
    assert job["environment"] == "ant"
    assert job["algorithm"] == "ppo-sb3"
    assert job["resolved_config"]["params"]["seed"] == 42
    assert job["resolved_config"]["params"]["total_timesteps"] == 100_000


def test_unknown_preset_rejected(client, sender, login):
    headers = login(_email())
    res = client.post("/jobs", json={"preset": "nope"}, headers=headers)
    assert res.status_code == 422
    assert res.json()["detail"]["field"] == "preset"


def test_resolved_config_visible_on_get(client, sender, login):
    headers = login(_email())
    created = client.post(
        "/jobs",
        json={"environment": "halfcheetah", "algorithm": "ppo-sb3", "params": {"learning_rate": 5e-4}},
        headers=headers,
    ).json()
    res = client.get(f"/jobs/{created['id']}", headers=headers)
    assert res.status_code == 200
    cfg = res.json()["resolved_config"]
    assert cfg["environment"] == "halfcheetah"
    assert cfg["params"]["learning_rate"] == 5e-4
    assert cfg["params"]["total_timesteps"] == 100_000
