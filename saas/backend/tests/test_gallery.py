from __future__ import annotations

import uuid
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from app import catalog, main
from app.models import Job, STATUS_QUEUED
from app.orchestration import NebiusBackend
from app.settings import GallerySettings, NebiusSettings, SettingsError
from app.store import JobStore

EXPECTED_IDS = [
    "go1-walker",
    "ant-explorer",
    "halfcheetah-sprint",
    "hopper-balance",
    "walker2d-stride",
    "g1-rough-terrain",
    "reacher-target",
]


@pytest.fixture()
def enabled_gallery(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "_gallery_settings", GallerySettings(enabled=True))


def _email() -> str:
    return f"gallery-{uuid.uuid4().hex[:8]}@example.com"


def test_catalog_has_exact_order_metadata_and_one_recommendation(
    client, enabled_gallery
) -> None:
    result = client.get("/training-options").json()
    assert result["gallery_enabled"] is True
    assert [item["id"] for item in result["examples"]] == EXPECTED_IDS
    for example in result["examples"]:
        assert example["avatar"] == f"/avatars/{example['id']}.svg"
        assert example["backend_label"] in {"SB3 PPO", "MJX / JAX PPO"}
        assert example["hardware_label"]
        assert example["success_criterion"]
        assert example["primary_metric"]
        assert example["recommended_profile"]
        if example["workload_profiles"]:
            assert (
                sum(bool(item["recommended"]) for item in example["workload_profiles"])
                == 1
            )
    hopper = next(item for item in result["examples"] if item["id"] == "hopper-balance")
    assert hopper["recommended_params"]["total_timesteps"] == 2_000_000
    assert catalog.JOB_SPECS[("hopper", "ppo-sb3")].max_total_timesteps == 2_000_000
    walker = next(
        item for item in result["examples"] if item["id"] == "walker2d-stride"
    )
    assert walker["recommended_params"]["total_timesteps"] == 2_000_000
    assert catalog.JOB_SPECS[("walker2d", "ppo-sb3")].max_total_timesteps == 2_000_000


def test_gallery_submission_uses_only_server_owned_identity_profile_and_seed(
    client, login, enabled_gallery
) -> None:
    headers = login(_email())
    response = client.post(
        "/jobs",
        json={
            "gallery_example_id": "go1-walker",
            "gallery_profile_id": "go1-mjx-standard",
            "params": {"seed": 42},
        },
        headers=headers,
    )
    assert response.status_code == 201
    job = response.json()
    assert job["gallery_example_id"] == "go1-walker"
    assert job["environment"] == "go1"
    assert job["algorithm"] == "ppo-mjx"
    assert job["preset"] == "go1-mjx-standard"
    assert job["resolved_config"]["params"] == {
        "seed": 42,
        "total_timesteps": 25_000_000,
    }
    persisted = client.get(f"/jobs/{job['id']}", headers=headers).json()
    assert persisted["gallery_example_id"] == "go1-walker"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (
            {"gallery_example_id": "hopper-balance", "environment": "go1"},
            "gallery_example_id",
        ),
        (
            {"gallery_example_id": "hopper-balance", "algorithm": "ppo-mjx"},
            "gallery_example_id",
        ),
        (
            {"gallery_example_id": "hopper-balance", "params": {"image": "evil"}},
            "image",
        ),
        (
            {
                "gallery_example_id": "hopper-balance",
                "gallery_profile_id": "go1-mjx-quality",
            },
            "gallery_profile_id",
        ),
        ({"gallery_example_id": "missing"}, "gallery_example_id"),
        ({"preset": "go1-mjx-quick"}, "gallery_example_id"),
    ],
)
def test_gallery_rejects_unsafe_or_stale_overrides(
    client, login, enabled_gallery, body, field
) -> None:
    response = client.post("/jobs", json=body, headers=login(_email()))
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == field


def test_stale_acceptance_revision_is_hidden_and_rejected(monkeypatch) -> None:
    original = catalog.JOB_SPECS[("hopper", "ppo-sb3")]
    monkeypatch.setitem(
        catalog.JOB_SPECS,
        ("hopper", "ppo-sb3"),
        replace(original, acceptance_revision="stale"),
    )
    visible = catalog.serialize(gallery_enabled=True)["examples"]
    assert "hopper-balance" not in [item["id"] for item in visible]
    with pytest.raises(catalog.ValidationError, match="not accepted"):
        catalog.resolve_gallery("hopper-balance", {})


def test_old_jobs_schema_migrates_without_rewriting_historical_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "old.db"
    historical = Job(
        id="b" * 32,
        tenant_id="owner@example.com",
        preset="go1-mjx-quick",
        environment="go1",
        algorithm="ppo-mjx",
        resolved_config={"environment": "go1", "algorithm": "ppo-mjx", "params": {}},
        status=STATUS_QUEUED,
        created_at="2026-07-13T00:00:00Z",
        updated_at="2026-07-13T00:00:00Z",
    ).model_dump(mode="json")
    historical.pop("gallery_example_id")
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, data TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO jobs (id, tenant_id, data) VALUES (?, ?, ?)",
        (historical["id"], historical["tenant_id"], json.dumps(historical)),
    )
    connection.commit()
    connection.close()

    store = JobStore(str(database))
    migrated = store.get("owner@example.com", historical["id"])
    assert migrated is not None
    assert migrated.gallery_example_id is None
    check = sqlite3.connect(database)
    assert "gallery_example_id" in {
        row[1] for row in check.execute("PRAGMA table_info(jobs)")
    }
    check.close()


def test_gallery_settings_fail_fast_for_mutable_production_images() -> None:
    with pytest.raises(SettingsError, match="SIM2POLICY_JOB_IMAGE"):
        GallerySettings.from_env(
            {
                "SAAS_GALLERY_ENABLED": "true",
                "SIM2POLICY_JOB_IMAGE": "registry/sim2policy:latest",
                "SIM2POLICY_MJX_JOB_IMAGE": "registry/sim2policy:mjx-abcdef0",
            },
            orchestration_backend="nebius",
        )


class _UnusedClient:
    def create_job(self, submission):  # pragma: no cover - build-only test
        raise AssertionError(submission)

    def get_job_state(self, job_id):  # pragma: no cover - build-only test
        raise AssertionError(job_id)


class _Reader:
    pass


def test_sb3_and_mjx_gallery_submissions_select_distinct_server_runtimes() -> None:
    settings = NebiusSettings(
        project_id="project",
        subnet_id="subnet",
        job_image="registry/sim2policy:sb3-abcdef0",
        mjx_job_image="registry/sim2policy:mjx-abcdef0",
        s3_secret_selector="secret/version",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
        s3_endpoint_url="https://s3.example",
        s3_region="region",
        s3_bucket="bucket",
    )
    backend = NebiusBackend(settings, _UnusedClient(), _Reader())

    def job(example_id: str) -> Job:
        resolved = catalog.resolve_gallery(example_id, {"seed": 7})
        return Job(
            id="a" * 32,
            tenant_id="owner@example.com",
            preset=resolved["profile"],
            environment=resolved["environment"],
            algorithm=resolved["algorithm"],
            resolved_config=resolved,
            gallery_example_id=example_id,
            status=STATUS_QUEUED,
            created_at="2026-07-14T00:00:00Z",
            updated_at="2026-07-14T00:00:00Z",
        )

    sb3 = backend.build_submission(job("hopper-balance"))
    assert sb3.image == settings.job_image
    assert (sb3.platform, sb3.preset) == ("cpu-d3", "8vcpu-32gb")
    assert sb3.args[:2] == ["-m", "sim2policy.hosted_sb3"]
    assert "--gallery-example-id" in sb3.args
    assert "reporting.hourly_rate=0.1984" in sb3.args
    assert 'reporting.rate_date="2026-07-14"' in sb3.args
    mjx = backend.build_submission(job("go1-walker"))
    assert mjx.image == settings.mjx_job_image
    assert (mjx.platform, mjx.preset) == ("gpu-h100-sxm", "1gpu-16vcpu-200gb")
    assert mjx.args[:2] == ["-m", "sim2policy.hosted_mjx"]
    assert "reporting.hourly_rate=3.85" in mjx.args
