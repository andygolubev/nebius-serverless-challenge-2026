"""SQLite connection setup for the persistent stores.

The database file lives at SAAS_DB_PATH (a PVC-mounted path in the cluster); without it
the backend falls back to a local file so development and tests need no configuration.
Each store opens its own connection to the same file — WAL mode lets them coexist and
the stores serialize their own access with locks.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

DEFAULT_DB_PATH = "saas.db"
_CONNECT_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    gallery_example_id TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_tenant ON jobs (tenant_id);
CREATE TABLE IF NOT EXISTS artifacts (
    job_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS robot_assets (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    digest TEXT NOT NULL,
    robot_type TEXT NOT NULL,
    data TEXT NOT NULL,
    xml_content TEXT NOT NULL,
    deleted_at REAL
);
CREATE INDEX IF NOT EXISTS robot_assets_tenant ON robot_assets (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS robot_assets_active_digest
    ON robot_assets (tenant_id, robot_type, digest) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS robot_setups (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    robot_id TEXT NOT NULL,
    digest TEXT NOT NULL,
    data TEXT NOT NULL,
    deleted_at REAL
);
CREATE INDEX IF NOT EXISTS robot_setups_tenant ON robot_setups (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS robot_setups_active_digest
    ON robot_setups (tenant_id, digest) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS preparation_attempts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    setup_id TEXT NOT NULL,
    robot_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS preparation_attempts_tenant_setup
    ON preparation_attempts (tenant_id, setup_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS preparation_attempts_active_fingerprint
    ON preparation_attempts (tenant_id, setup_id, fingerprint)
    WHERE state IN ('queued', 'preparing');
CREATE TABLE IF NOT EXISTS custom_training_requests (
    tenant_id TEXT NOT NULL,
    setup_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    job_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, setup_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS custom_training_requests_tenant_created
    ON custom_training_requests (tenant_id, created_at);
CREATE TABLE IF NOT EXISTS analytics_visits (
    id TEXT PRIMARY KEY,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    ip_hash TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    referrer TEXT NOT NULL,
    is_bot INTEGER NOT NULL CHECK (is_bot IN (0, 1))
);
CREATE INDEX IF NOT EXISTS analytics_visits_last_seen ON analytics_visits (last_seen);
CREATE INDEX IF NOT EXISTS analytics_visits_ip_hash ON analytics_visits (ip_hash);
CREATE TABLE IF NOT EXISTS analytics_page_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id TEXT NOT NULL,
    view TEXT NOT NULL,
    entity_id TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (visit_id) REFERENCES analytics_visits(id)
);
CREATE INDEX IF NOT EXISTS analytics_page_views_created_at ON analytics_page_views (created_at);
CREATE INDEX IF NOT EXISTS analytics_page_views_view ON analytics_page_views (view);
CREATE TABLE IF NOT EXISTS analytics_daily (
    day TEXT PRIMARY KEY,
    visits INTEGER NOT NULL,
    page_views INTEGER NOT NULL,
    unique_visitors INTEGER NOT NULL,
    bot_visits INTEGER NOT NULL
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive migrations to databases created by earlier releases."""
    job_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(jobs)")}
    if "gallery_example_id" not in job_columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN gallery_example_id TEXT")


def resolve_path(db_path: str | None = None) -> str:
    return db_path or os.environ.get("SAAS_DB_PATH") or DEFAULT_DB_PATH


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a connection with WAL + schema; safe for cross-thread use behind a lock."""
    path = resolve_path(db_path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Only first-open configuration is serialized. Once returned, each store has
    # its own connection and WAL provides the intended concurrent access.
    with _CONNECT_LOCK:
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        try:
            # Install the busy handler before WAL negotiation: concurrent first-open
            # connections can otherwise race on the journal-mode schema lock.
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            _migrate(conn)
        except Exception:
            conn.close()
            raise
    return conn
