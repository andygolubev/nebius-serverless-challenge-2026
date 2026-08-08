from __future__ import annotations

import sqlite3
import time
import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import analytics, db, main
from app.settings import AnalyticsSettings, SettingsError
from app.store import AnalyticsStore


def test_analytics_settings_from_env_is_bounded() -> None:
    assert AnalyticsSettings.from_env({}) == AnalyticsSettings(None, 90, 30)
    with pytest.raises(SettingsError, match="must be an integer"):
        AnalyticsSettings.from_env({"SAAS_ANALYTICS_RETENTION_DAYS": "invalid"})
    with pytest.raises(SettingsError, match="must be between"):
        AnalyticsSettings.from_env({"SAAS_ANALYTICS_SESSION_GAP_MINUTES": "0"})


def test_client_address_prefers_valid_forwarded_address_and_falls_back() -> None:
    app = FastAPI()

    @app.get("/")
    def address(request: Request):
        return {"address": analytics.client_address(request)}

    client = TestClient(app)
    assert client.get("/", headers={"X-Forwarded-For": "203.0.113.7, 10.42.0.9"}).json() == {"address": "203.0.113.7"}
    assert client.get("/", headers={"X-Forwarded-For": "not-an-address"}).json() == {"address": "testclient"}


def test_hashing_and_bot_classification() -> None:
    assert analytics.hash_address("203.0.113.7", "salt") == analytics.hash_address("203.0.113.7", "salt")
    assert analytics.hash_address("203.0.113.7", None) is None
    assert analytics.is_bot("Googlebot/2.1")
    assert analytics.is_bot("")
    assert not analytics.is_bot("Mozilla/5.0")


def test_store_reuses_valid_visit_and_replaces_stale_or_forged_ids(tmp_path) -> None:
    store = AnalyticsStore(str(tmp_path / "analytics.db"), session_gap_minutes=30)
    visit_id = str(uuid.uuid4())
    assert store.record(visit_id, "showcase", None, "hash-a", "agent", "", False, 1_000) == visit_id
    assert store.record(visit_id, "about", None, "hash-a", "agent", "", False, 1_001) == visit_id
    forged = store.record(visit_id, "terms", None, "hash-b", "agent", "", False, 1_002)
    stale = store.record(visit_id, "login", None, "hash-a", "agent", "", False, 3_000)
    assert forged != visit_id and stale != visit_id and forged != stale
    rows = store._conn.execute("SELECT id, ip_hash FROM analytics_visits ORDER BY first_seen").fetchall()
    assert len(rows) == 3
    assert all("203.0.113.7" not in value for row in rows for value in row)
    assert store._conn.execute("SELECT COUNT(*) FROM analytics_page_views").fetchone()[0] == 4


def test_collect_is_always_empty_204(monkeypatch, tmp_path, client) -> None:
    store = AnalyticsStore(str(tmp_path / "collect.db"))
    monkeypatch.setattr(main, "_analytics_store", store)
    monkeypatch.setattr(main, "_analytics_settings", AnalyticsSettings("salt", 90, 30))
    response = client.post(
        "/analytics/collect",
        json={"visit_id": str(uuid.uuid4()), "view": "showcase", "entity_id": "x" * 200},
        headers={"X-Forwarded-For": "203.0.113.7", "User-Agent": "Mozilla/5.0"},
    )
    assert response.status_code == 204 and response.content == b""
    row = store._conn.execute("SELECT ip_hash, entity_id FROM analytics_visits JOIN analytics_page_views ON analytics_visits.id = analytics_page_views.visit_id").fetchone()
    assert row is not None and row[0] != "203.0.113.7" and len(row[1]) == 128
    monkeypatch.setattr(main, "_analytics_store", object())
    assert client.post("/analytics/collect", json={"view": "unknown"}).status_code == 204
    assert client.post("/analytics/collect", json={"view": "showcase", "entity_id": "x" * 10_000}).status_code == 204


def test_prune_rolls_up_only_analytics_and_is_idempotent(tmp_path) -> None:
    path = str(tmp_path / "prune.db")
    conn = db.connect(path)
    conn.execute("INSERT INTO users (email, created_at) VALUES (?, ?)", ("keep@example.test", 1))
    store = AnalyticsStore(path)
    old = time.time() - 100 * 24 * 60 * 60
    store.record(str(uuid.uuid4()), "showcase", None, "old-hash", "agent", "", False, old)
    store.record(str(uuid.uuid4()), "about", None, "new-hash", "agent", "", False, time.time())
    store.prune(90, time.time())
    first = store._conn.execute("SELECT * FROM analytics_daily").fetchall()
    store.prune(90, time.time())
    assert store._conn.execute("SELECT * FROM analytics_daily").fetchall() == first
    assert store._conn.execute("SELECT COUNT(*) FROM analytics_visits").fetchone()[0] == 1
    assert conn.execute("SELECT email FROM users").fetchone()[0] == "keep@example.test"


def test_existing_database_schema_is_additive(tmp_path) -> None:
    path = str(tmp_path / "existing.db")
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE users (email TEXT PRIMARY KEY, created_at REAL NOT NULL)")
    legacy.execute("INSERT INTO users VALUES ('existing@example.test', 1)")
    legacy.commit()
    legacy.close()
    conn = db.connect(path)
    assert conn.execute("SELECT email FROM users").fetchone()[0] == "existing@example.test"
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'analytics_visits'").fetchone()[0] == "analytics_visits"
