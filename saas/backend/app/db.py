"""SQLite connection setup for the persistent stores.

The database file lives at SAAS_DB_PATH (a PVC-mounted path in the cluster); without it
the backend falls back to a local file so development and tests need no configuration.
Each store opens its own connection to the same file — WAL mode lets them coexist and
the stores serialize their own access with locks.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = "saas.db"

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
"""


def resolve_path(db_path: str | None = None) -> str:
    return db_path or os.environ.get("SAAS_DB_PATH") or DEFAULT_DB_PATH


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a connection with WAL + schema; safe for cross-thread use behind a lock."""
    path = resolve_path(db_path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Autocommit + single-statement operations; the callers hold their own locks,
    # sqlite's serialized mode covers the rest.
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn
