"""Restart survival: durable state must outlive the store objects (spec: saas-data-persistence)."""

from __future__ import annotations

import time

from app.models import ArtifactManifest, Job
from app.store import AuthStore, JobStore, Session


def _job(job_id: str, tenant: str) -> Job:
    return Job(
        id=job_id,
        tenant_id=tenant,
        environment="env",
        algorithm="algo",
        resolved_config={},
        status="completed",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def test_jobs_and_artifacts_survive_reopen(tmp_path):
    path = str(tmp_path / "saas.db")
    store = JobStore(path)
    store.put(_job("j1", "a@example.com"))
    store.set_artifacts(ArtifactManifest(job_id="j1", status="completed", metrics={"reward": 1.0}))

    reopened = JobStore(path)  # simulates a process restart
    job = reopened.get("a@example.com", "j1")
    assert job is not None and job.status == "completed"
    manifest = reopened.get_artifacts("j1")
    assert manifest is not None and manifest.metrics == {"reward": 1.0}


def test_tenant_isolation_survives_reopen(tmp_path):
    path = str(tmp_path / "saas.db")
    store = JobStore(path)
    store.put(_job("j1", "a@example.com"))
    store.put(_job("j2", "b@example.com"))

    reopened = JobStore(path)
    assert reopened.get("b@example.com", "j1") is None
    assert [j.id for j in reopened.list("a@example.com")] == ["j1"]


def test_session_and_user_survive_reopen(tmp_path):
    path = str(tmp_path / "saas.db")
    store = AuthStore(path)
    store.ensure_user("a@example.com")
    store.put_session(Session(token="tok", email="a@example.com", expires_at=time.time() + 3600))

    reopened = AuthStore(path)
    session = reopened.get_session("tok")
    assert session is not None and session.email == "a@example.com"
    user = reopened.ensure_user("a@example.com")
    assert user.created_at <= time.time()


def test_expired_session_not_resolved_after_reopen(tmp_path):
    path = str(tmp_path / "saas.db")
    store = AuthStore(path)
    store.put_session(Session(token="tok", email="a@example.com", expires_at=time.time() - 1))

    reopened = AuthStore(path)
    assert reopened.get_session("tok") is None
