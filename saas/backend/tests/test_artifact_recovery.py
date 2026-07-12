"""Lazy artifact-manifest recovery: completed jobs whose manifest is published
after completion (finalization pipeline) become servable on demand."""

from __future__ import annotations

import uuid

import pytest

from app import main
from app.models import STATUS_COMPLETED, STATUS_TRAINING, ArtifactManifest, Job


def _email() -> str:
    return f"{uuid.uuid4().hex[:10]}@example.com"


def _put_job(tenant: str, status: str) -> Job:
    now = main._now()
    job = Job(
        id=uuid.uuid4().hex,
        tenant_id=tenant,
        environment="go1",
        algorithm="ppo-mjx",
        resolved_config={},
        status=status,
        created_at=now,
        updated_at=now,
    )
    main._store.put(job)
    return job


class StubReader:
    """Counts calls; returns a fixed manifest, None, or raises."""

    def __init__(self, manifest: ArtifactManifest | None = None, error: Exception | None = None):
        self.manifest = manifest
        self.error = error
        self.calls = 0

    def read_manifest(self, job_id: str, run_id: str) -> ArtifactManifest | None:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.manifest


class StubBackend:
    name = "stub"

    def __init__(self, reader):
        self.artifact_reader = reader


@pytest.fixture()
def backend_reader(monkeypatch):
    """Install a stub backend with the given reader; returns the installer."""

    def _install(reader):
        monkeypatch.setattr(main, "_backend", StubBackend(reader))
        return reader

    return _install


def test_completed_job_recovers_and_caches_manifest(client, sender, login, backend_reader):
    email = _email()
    headers = login(email)
    job = _put_job(email, STATUS_COMPLETED)
    manifest = ArtifactManifest(
        job_id=job.id,
        status=STATUS_COMPLETED,
        metrics={"mean_reward": 28.463},
        media=[f"sim2policy/{job.id}/videos/final.mp4"],
    )
    reader = backend_reader(StubReader(manifest))

    res = client.get(f"/jobs/{job.id}/artifacts", headers=headers)
    assert res.status_code == 200
    assert res.json()["metrics"]["mean_reward"] == 28.463
    assert reader.calls == 1

    # Second request is served from the durable cache, not the reader.
    res = client.get(f"/jobs/{job.id}/artifacts", headers=headers)
    assert res.status_code == 200
    assert reader.calls == 1
    assert main._store.get_artifacts(job.id) is not None


def test_reader_miss_keeps_409(client, sender, login, backend_reader, caplog):
    email = _email()
    headers = login(email)
    job = _put_job(email, STATUS_COMPLETED)
    reader = backend_reader(StubReader(manifest=None))

    res = client.get(f"/jobs/{job.id}/artifacts", headers=headers)
    assert res.status_code == 409
    assert reader.calls == 1
    assert main._store.get_artifacts(job.id) is None
    assert "lazy artifact manifest not found" in caplog.text


def test_reader_error_degrades_to_409(client, sender, login, backend_reader):
    email = _email()
    headers = login(email)
    job = _put_job(email, STATUS_COMPLETED)
    backend_reader(StubReader(error=RuntimeError("s3 unavailable")))

    res = client.get(f"/jobs/{job.id}/artifacts", headers=headers)
    assert res.status_code == 409


def test_non_completed_job_never_triggers_reader(client, sender, login, backend_reader):
    email = _email()
    headers = login(email)
    job = _put_job(email, STATUS_TRAINING)
    reader = backend_reader(StubReader(ArtifactManifest(job_id=job.id, status=STATUS_COMPLETED)))

    res = client.get(f"/jobs/{job.id}/artifacts", headers=headers)
    assert res.status_code == 409
    assert reader.calls == 0


def test_backend_without_reader_keeps_409(client, sender, login, backend_reader):
    # Mock backend exposes artifact_reader = None; behavior is unchanged.
    email = _email()
    headers = login(email)
    job = _put_job(email, STATUS_COMPLETED)
    backend_reader(None)

    res = client.get(f"/jobs/{job.id}/artifacts", headers=headers)
    assert res.status_code == 409
