"""SQLite-backed, tenant-scoped stores for users, sessions, jobs, and artifacts.

Durable state (users, sessions, jobs, artifact manifests) lives in the SQLite file from
SAAS_DB_PATH so it survives restarts and redeploys. Pending one-time codes and rate-limit
windows stay in process memory: they live minutes by design and are safe to lose.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from . import db
from .models import ArtifactManifest, Job


class JobStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._conn = db.connect(db_path)

    def put(self, job: Job) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO jobs (id, tenant_id, data) VALUES (?, ?, ?)",
                (job.id, job.tenant_id, job.model_dump_json()),
            )

    def get(self, tenant_id: str, job_id: str) -> Job | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT tenant_id, data FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        # Tenant isolation: never reveal another tenant's job.
        if row is None or row[0] != tenant_id:
            return None
        return Job.model_validate_json(row[1])

    def list(self, tenant_id: str) -> list[Job]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM jobs WHERE tenant_id = ?", (tenant_id,)
            ).fetchall()
        return [Job.model_validate_json(r[0]) for r in rows]

    def list_active(self) -> list[Job]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM jobs").fetchall()
        jobs = [Job.model_validate_json(row[0]) for row in rows]
        return [job for job in jobs if job.status not in {"completed", "failed"}]

    def set_artifacts(self, manifest: ArtifactManifest) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO artifacts (job_id, data) VALUES (?, ?)",
                (manifest.job_id, manifest.model_dump_json()),
            )

    def get_artifacts(self, job_id: str) -> ArtifactManifest | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM artifacts WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return ArtifactManifest.model_validate_json(row[0])


@dataclass
class PendingCode:
    """A hashed one-time login code awaiting verification."""

    code_hash: str
    expires_at: float
    attempts: int = 0


@dataclass
class Session:
    token: str
    email: str
    expires_at: float


@dataclass
class User:
    email: str
    created_at: float


class AuthStore:
    """Users and sessions in SQLite; pending codes and rate limiting in memory.

    Single-replica: one process owns the database file, same as JobStore.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._conn = db.connect(db_path)
        self._codes: dict[str, PendingCode] = {}
        self._request_times: dict[str, list[float]] = {}

    # -- rate limiting (sliding window) --

    def allow_code_request(self, email: str, limit: int, window_seconds: float) -> bool:
        now = time.time()
        with self._lock:
            times = [t for t in self._request_times.get(email, []) if now - t < window_seconds]
            if len(times) >= limit:
                self._request_times[email] = times
                return False
            times.append(now)
            self._request_times[email] = times
            return True

    # -- pending codes --

    def set_code(self, email: str, code: PendingCode) -> None:
        with self._lock:
            self._codes[email] = code

    def get_code(self, email: str) -> PendingCode | None:
        with self._lock:
            return self._codes.get(email)

    def delete_code(self, email: str) -> None:
        with self._lock:
            self._codes.pop(email, None)

    def bump_attempts(self, email: str) -> int:
        """Increment and return the attempt count for the email's pending code."""
        with self._lock:
            code = self._codes.get(email)
            if code is None:
                return 0
            code.attempts += 1
            return code.attempts

    # -- users --

    def ensure_user(self, email: str) -> User:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO users (email, created_at) VALUES (?, ?)",
                (email, time.time()),
            )
            row = self._conn.execute(
                "SELECT email, created_at FROM users WHERE email = ?", (email,)
            ).fetchone()
        return User(email=row[0], created_at=row[1])

    # -- sessions --

    def put_session(self, session: Session) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO sessions (token, email, expires_at) VALUES (?, ?, ?)",
                (session.token, session.email, session.expires_at),
            )

    def get_session(self, token: str) -> Session | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT token, email, expires_at FROM sessions WHERE token = ?", (token,)
            ).fetchone()
            if row is None:
                return None
            if row[2] < time.time():
                self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
        return Session(token=row[0], email=row[1], expires_at=row[2])

    def delete_session(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
