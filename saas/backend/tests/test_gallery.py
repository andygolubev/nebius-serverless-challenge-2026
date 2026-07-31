"""The public showcase API: anonymous reads, evidence gating, and its hard limits."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from app import catalog, main, showcase
from app.artifacts import S3ArtifactReader
from app.models import STATUS_QUEUED, ArtifactManifest, Job
from app.settings import ShowcaseSettings
from app.showcase import ShowcaseService
from app.store import JobStore
from tests.test_gallery_artifacts import MemoryS3, SHOWCASE_METRICS

GALLERY_ORDER = [
    "go1-walker",
    "ant-explorer",
    "halfcheetah-sprint",
    "hopper-balance",
    "walker2d-stride",
    "g1-rough-terrain",
    "reacher-target",
]


def _email() -> str:
    return f"showcase-{uuid.uuid4().hex[:8]}@nebius.com"


@pytest.fixture()
def published(monkeypatch, store):
    """Wire the API's showcase at a complete in-memory run for one example."""
    s3 = MemoryS3()

    class Backend:
        artifact_reader = S3ArtifactReader(s3, "bucket")

    monkeypatch.setitem(catalog.SHOWCASE_RUNS, "hopper-balance", "gallery-run")
    catalog.validate_showcase_runs()
    monkeypatch.setattr(
        main,
        "_showcase",
        ShowcaseService(store, Backend(), ShowcaseSettings(enabled=True)),
    )
    yield s3
    monkeypatch.undo()
    catalog.validate_showcase_runs()


# -- anonymous catalog reads --


def test_showcase_returns_200_with_an_empty_list_when_nothing_validates(client):
    """The normal state until the curated runs land: correct, not an error."""
    res = client.get("/showcase")
    assert res.status_code == 200
    assert res.json() == {"examples": []}


def test_pinned_placeholders_resolve_to_no_run_at_all():
    # Placeholders are safe identifiers, so they pass validation, but they must never
    # become a storage read. Accepted examples publish independently of the rest, so
    # an example that has been curated resolves to its run while the others stay dark.
    assert set(catalog.validate_showcase_runs()) == set(GALLERY_ORDER)
    for example_id in GALLERY_ORDER:
        pinned = catalog.SHOWCASE_RUNS[example_id]
        resolved = catalog.resolve_showcase_run(example_id)
        if catalog.is_pending_run(pinned):
            assert resolved is None
        else:
            assert resolved == pinned


def test_showcase_needs_no_session_and_ignores_one(client, sender, login, published):
    anonymous = client.get("/showcase")
    assert anonymous.status_code == 200
    assert [item["id"] for item in anonymous.json()["examples"]] == ["hopper-balance"]

    # A signed-in tenant, a forged token, and an anonymous caller get the same bytes.
    with_session = client.get("/showcase", headers=login(_email()))
    forged = client.get("/showcase", headers={"Authorization": "Bearer nonsense"})
    assert with_session.content == anonymous.content
    assert forged.content == anonymous.content


def test_published_entry_carries_display_and_evidence_metadata(client, published):
    entry = client.get("/showcase").json()["examples"][0]
    assert entry["label"] == "Hopper Balance"
    assert entry["avatar"] == "/avatars/hopper-balance.svg"
    assert entry["backend_label"] == "sb3"
    assert entry["observed_duration"] and entry["observed_cost"]
    assert entry["evaluation"]["criterion"]
    assert entry["has_media"] is True
    assert entry["executed_config"]["platform"] == "cpu-d3"
    # No submittable contract is advertised on an entry.
    for absent in ("recommended_params", "optional_params", "recommended_profile"):
        assert absent not in entry


class _MultiRunReader:
    """Routes each pinned run id at its own in-memory bucket."""

    def __init__(self, clients: dict[str, MemoryS3]) -> None:
        self._readers = {
            f"run-{example_id}": S3ArtifactReader(value, "bucket")
            for example_id, value in clients.items()
        }

    def read_showcase_manifest(self, run_id: str):
        reader = self._readers.get(run_id)
        return None if reader is None else reader.read_showcase_manifest(run_id)

    def presigned_url(self, key, **kwargs):
        return f"https://objects.example/{key}"


def test_entries_follow_documented_gallery_order(client, monkeypatch, store):
    """Ordering follows the catalog, not manifest or storage iteration order."""
    clients = {
        example_id: MemoryS3(
            run=f"sim2policy/run-{example_id}",
            metrics={
                **SHOWCASE_METRICS,
                "environment": showcase.CANONICAL_ENVIRONMENTS[example_id],
                "backend": "mjx" if example_id in {"go1-walker", "g1-rough-terrain"} else "sb3",
                "runtime_seconds": 1.0,
            },
        )
        for example_id in GALLERY_ORDER
    }

    class Backend:
        artifact_reader = _MultiRunReader(clients)

    for example_id in GALLERY_ORDER:
        monkeypatch.setitem(catalog.SHOWCASE_RUNS, example_id, f"run-{example_id}")
    catalog.validate_showcase_runs()
    monkeypatch.setattr(
        main,
        "_showcase",
        ShowcaseService(store, Backend(), ShowcaseSettings(enabled=True)),
    )
    got = [item["id"] for item in client.get("/showcase").json()["examples"]]
    monkeypatch.undo()
    catalog.validate_showcase_runs()
    assert got == GALLERY_ORDER


def test_response_leaks_no_tenant_or_storage_identity(client, published):
    body = client.get("/showcase").text
    detail = client.get("/showcase/hopper-balance").text
    for leak in ("sim2policy/", "bucket", "@nebius.com", "AKIA", "signed=1", "gallery-run"):
        assert leak not in body, f"catalog leaks {leak}"
        assert leak not in detail, f"detail leaks {leak}"


# -- anonymous detail reads --


def test_detail_reports_evaluation_separately_from_completion(client, published):
    detail = client.get("/showcase/hopper-balance").json()
    assert detail["status"] == "completed"
    assert detail["evaluation"]["success"] is True
    assert detail["metrics"]["aggregate"]["mean_reward"] == 1234.5
    assert detail["metrics"]["checkpoint"] == "final-000001000000.zip"


@pytest.mark.parametrize(
    "example_id",
    ["ghost", "go1-walker", "..%2F..%2Fetc%2Fpasswd"],
    ids=["unknown", "unpublished", "traversal"],
)
def test_unknown_hidden_and_gate_failing_entries_are_indistinguishable(
    client, published, example_id
):
    res = client.get(f"/showcase/{example_id}")
    assert res.status_code == 404
    # The message must not reveal which case applied (Starlette's own unmatched-path
    # 404 says "Not Found"; the handler's says "example not found").
    assert str(res.json()["detail"]).lower() in {"not found", "example not found"}


# -- artifact delivery --


def test_anonymous_artifact_access_redirects_to_a_presigned_url(client, published):
    res = client.get(
        "/showcase/hopper-balance/artifacts/video_final", follow_redirects=False
    )
    assert res.status_code == 307
    assert res.headers["location"].startswith("https://objects.example/")
    call = published.presigned[-1]
    assert call["expires_in"] <= 300
    assert call["params"]["ResponseContentType"] == "video/mp4"


def test_artifact_download_uses_a_safe_filename(client, published):
    res = client.get(
        "/showcase/hopper-balance/artifacts/policy_bundle?download=true",
        follow_redirects=False,
    )
    assert res.status_code == 307
    disposition = published.presigned[-1]["params"]["ResponseContentDisposition"]
    assert disposition == 'attachment; filename="policy-bundle.zip"'


@pytest.mark.parametrize(
    "artifact_id", ["demo_recording", "backend_comparison", "anything"]
)
def test_artifact_not_in_the_validated_manifest_is_404(client, published, artifact_id):
    assert client.get(
        f"/showcase/hopper-balance/artifacts/{artifact_id}"
    ).status_code == 404


# -- the hard limits --


def test_no_showcase_route_creates_or_mutates_anything(client, sender, login, published):
    """No method, parameter, or header turns a showcase route into a write."""
    headers = login(_email())
    before_jobs = len(client.get("/jobs", headers=headers).json())
    before_objects = dict(published.objects)

    routes = [
        "/showcase",
        "/showcase/hopper-balance",
        "/showcase/hopper-balance/artifacts/video_final",
    ]
    for route in routes:
        for method in ("post", "put", "patch"):
            res = getattr(client, method)(route, json={"start": True}, headers=headers)
            assert res.status_code in {404, 405}, f"{method.upper()} {route}"
        assert client.delete(route, headers=headers).status_code in {404, 405}
        # Training-shaped query parameters must not be honoured either.
        assert client.get(
            f"{route}?start=true&train=1&gallery_example_id=hopper-balance",
            headers=headers,
            follow_redirects=False,
        ).status_code in {200, 307}

    assert len(client.get("/jobs", headers=headers).json()) == before_jobs
    assert published.objects == before_objects


def test_showcase_routes_cannot_resolve_a_tenant_run(client, sender, login, published):
    """A tenant job or run identity substituted anywhere 404s and reads nothing."""
    email = _email()
    headers = login(email)
    job_id = uuid.uuid4().hex
    main._store.put(
        Job(
            id=job_id,
            tenant_id=email,
            environment="uploaded-biped",
            algorithm="ppo-sb3",
            resolved_config={"job_kind": "custom-robot"},
            status=STATUS_QUEUED,
            created_at="2026-07-26T00:00:00+00:00",
            updated_at="2026-07-26T00:00:00+00:00",
            job_kind="custom-robot",
        )
    )
    reads_before = len(published.presigned)

    for candidate in (job_id, "gallery-run"):
        assert client.get(f"/showcase/{candidate}").status_code == 404
        assert (
            client.get(f"/showcase/{candidate}/artifacts/video_final").status_code == 404
        )
    # No presigned read was performed for any caller-supplied identity.
    assert len(published.presigned) == reads_before

    # And the tenant route rejects a showcase example id under normal ownership rules.
    assert client.get("/jobs/hopper-balance", headers=headers).status_code == 404


def test_showcase_and_tenant_manifests_cannot_cross_in_the_shared_cache(store, pinned):
    """Both live in the `artifacts` table; a lookup must not return the other's."""
    tenant_job_id = uuid.uuid4().hex
    store.set_artifacts(
        ArtifactManifest(
            job_id=tenant_job_id, status="completed", metrics={"tenant": True}
        )
    )

    class Backend:
        artifact_reader = S3ArtifactReader(MemoryS3(), "bucket")

    service = ShowcaseService(store, Backend(), ShowcaseSettings(enabled=True))
    detail = service.detail("hopper-balance")
    assert detail is not None
    assert detail["metrics"].get("tenant") is None

    # The pinned identity is distinct from the tenant job identity space by construction.
    assert catalog._TENANT_JOB_ID_RE.fullmatch(tenant_job_id)
    assert not catalog._TENANT_JOB_ID_RE.fullmatch("gallery-run")
    # And the tenant's cached manifest is untouched.
    assert store.get_artifacts(tenant_job_id).metrics == {"tenant": True}


def test_pinned_identities_colliding_with_the_tenant_space_are_refused(monkeypatch):
    collision = uuid.uuid4().hex  # 32 lowercase hex: indistinguishable from a job id
    monkeypatch.setitem(catalog.SHOWCASE_RUNS, "reacher-target", collision)
    valid = catalog.validate_showcase_runs()
    monkeypatch.undo()
    catalog.validate_showcase_runs()
    assert "reacher-target" not in valid


def test_duplicate_pinned_identities_refuse_both_claims(monkeypatch):
    monkeypatch.setitem(catalog.SHOWCASE_RUNS, "ant-explorer", "shared-run")
    monkeypatch.setitem(catalog.SHOWCASE_RUNS, "hopper-balance", "shared-run")
    valid = catalog.validate_showcase_runs()
    monkeypatch.undo()
    catalog.validate_showcase_runs()
    # If two examples claim the same run, neither claim is trustworthy.
    assert "ant-explorer" not in valid and "hopper-balance" not in valid


def test_unsafe_pinned_identity_is_refused_without_failing_the_service(monkeypatch):
    monkeypatch.setitem(catalog.SHOWCASE_RUNS, "walker2d-stride", "../escape")
    valid = catalog.validate_showcase_runs()
    monkeypatch.undo()
    catalog.validate_showcase_runs()
    assert "walker2d-stride" not in valid
    # The other six entries are unaffected: one bad literal is not fatal.
    assert len(valid) == len(GALLERY_ORDER) - 1


def test_storage_failure_degrades_without_leaking_or_5xxing(client, monkeypatch, store):
    class Exploding:
        def read_showcase_manifest(self, run_id):
            raise RuntimeError("s3://sim2policy-artifacts secret-key-AKIA boom")

    class Backend:
        artifact_reader = Exploding()

    monkeypatch.setitem(catalog.SHOWCASE_RUNS, "hopper-balance", "gallery-run")
    catalog.validate_showcase_runs()
    monkeypatch.setattr(
        main,
        "_showcase",
        ShowcaseService(store, Backend(), ShowcaseSettings(enabled=True)),
    )
    listed = client.get("/showcase")
    detail = client.get("/showcase/hopper-balance")
    monkeypatch.undo()
    catalog.validate_showcase_runs()

    assert listed.status_code == 200 and listed.json() == {"examples": []}
    assert detail.status_code == 404
    for leak in ("AKIA", "sim2policy-artifacts", "boom"):
        assert leak not in listed.text and leak not in detail.text


def test_absent_run_is_not_re_read_on_every_request(monkeypatch, store):
    """The negative cache keeps a permanently-missing run off the storage path."""

    class Counting:
        def __init__(self):
            self.calls = 0

        def read_showcase_manifest(self, run_id):
            self.calls += 1
            return None

    reader = Counting()

    class Backend:
        artifact_reader = reader

    monkeypatch.setitem(catalog.SHOWCASE_RUNS, "hopper-balance", "gallery-run")
    catalog.validate_showcase_runs()
    service = ShowcaseService(store, Backend(), ShowcaseSettings(enabled=True))
    for _ in range(5):
        assert service.detail("hopper-balance") is None
    monkeypatch.undo()
    catalog.validate_showcase_runs()
    assert reader.calls == 1


def test_rate_limit_bounds_an_abusive_client(client, monkeypatch):
    monkeypatch.setattr(main, "_showcase_limiter", showcase.RateLimiter(limit=3))
    assert [client.get("/showcase").status_code for _ in range(3)] == [200, 200, 200]
    assert client.get("/showcase").status_code == 429
    # A fresh budget serves the showcase again: the limit is a window, not a ban.
    monkeypatch.setattr(main, "_showcase_limiter", showcase.RateLimiter())
    assert client.get("/showcase").status_code == 200


def test_rate_limiter_is_per_client_address():
    limiter = showcase.RateLimiter(limit=2)
    assert limiter.allow("1.2.3.4") and limiter.allow("1.2.3.4")
    assert not limiter.allow("1.2.3.4")
    # A different client is unaffected by the first one's exhausted budget.
    assert limiter.allow("5.6.7.8")


# -- historical jobs stay readable --


def test_historical_gallery_job_keeps_its_identity_and_artifacts(client, sender, login):
    """A job created before gallery training was removed still reads normally."""
    email = _email()
    headers = login(email)
    job_id = uuid.uuid4().hex
    main._store.put(
        Job(
            id=job_id,
            tenant_id=email,
            preset="go1-mjx-quality",
            environment="go1",
            algorithm="ppo-mjx",
            resolved_config={
                "gallery_example_id": "go1-walker",
                "example": {
                    "id": "go1-walker",
                    "label": "Go1 Walker",
                    "avatar": "/avatars/go1-walker.svg",
                    "task": "Walk forward",
                },
                "environment": "go1",
                "algorithm": "ppo-mjx",
                "params": {"total_timesteps": 100_000_000},
            },
            status="completed",
            created_at="2026-07-14T00:00:00+00:00",
            updated_at="2026-07-14T00:00:00+00:00",
            gallery_example_id="go1-walker",
        )
    )
    main._store.set_artifacts(
        ArtifactManifest(
            job_id=job_id, status="completed", metrics={"aggregate": {"mean_reward": 31.5}}
        )
    )

    detail = client.get(f"/jobs/{job_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    # The persisted identity, label, and avatar all survive.
    assert body["gallery_example_id"] == "go1-walker"
    assert body["resolved_config"]["example"]["label"] == "Go1 Walker"
    assert body["resolved_config"]["example"]["avatar"] == "/avatars/go1-walker.svg"
    assert body["preset"] == "go1-mjx-quality"

    artifacts = client.get(f"/jobs/{job_id}/artifacts", headers=headers)
    assert artifacts.status_code == 200
    assert artifacts.json()["metrics"]["aggregate"]["mean_reward"] == 31.5

    assert any(row["id"] == job_id for row in client.get("/jobs", headers=headers).json())


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


def test_showcase_defaults_to_enabled_and_ignores_the_old_training_flag():
    assert ShowcaseSettings.from_env(env={}).enabled is True
    assert (
        ShowcaseSettings.from_env(env={"SAAS_SHOWCASE_ENABLED": "false"}).enabled is False
    )
    # The old flag gated spending GPU budget, not showing evidence. A deployment that
    # set it to false must still serve the public showcase.
    assert ShowcaseSettings.from_env(env={"SAAS_GALLERY_ENABLED": "false"}).enabled is True
    assert ShowcaseSettings.from_env(env={"SAAS_GALLERY_ENABLED": "true"}).enabled is True


def test_health_reports_the_showcase_switch(client):
    assert client.get("/health").json()["showcase"] in {"enabled", "disabled"}
