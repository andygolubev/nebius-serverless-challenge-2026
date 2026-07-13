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
from .models import ArtifactManifest, Job, RobotAsset, RobotSetup

ROBOT_QUOTA = 20
SETUP_QUOTA = 50


class QuotaExceeded(Exception):
    def __init__(self, field: str, limit: int) -> None:
        self.field = field
        self.limit = limit
        super().__init__(f"{field} quota of {limit} reached")


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


class RobotStore:
    """Transactional, tenant-scoped storage for immutable robots and setup drafts."""

    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._conn = db.connect(db_path)

    @staticmethod
    def _robot(row: tuple[str, str]) -> RobotAsset:
        return RobotAsset.model_validate_json(row[1]).model_copy(update={"tenant_id": row[0]})

    @staticmethod
    def _setup(row: tuple[str, str]) -> RobotSetup:
        return RobotSetup.model_validate_json(row[1]).model_copy(update={"tenant_id": row[0]})

    def create_robot(self, robot: RobotAsset, xml_content: str) -> tuple[RobotAsset, bool]:
        """Create once, or return the active same-tenant/type/content version."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute(
                    """SELECT tenant_id, data FROM robot_assets
                       WHERE tenant_id = ? AND robot_type = ? AND digest = ?
                         AND deleted_at IS NULL""",
                    (robot.tenant_id, robot.robot_type, robot.digest),
                ).fetchone()
                if existing is not None:
                    self._conn.execute("COMMIT")
                    return self._robot(existing), False
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM robot_assets WHERE tenant_id = ? AND deleted_at IS NULL",
                    (robot.tenant_id,),
                ).fetchone()[0]
                if count >= ROBOT_QUOTA:
                    raise QuotaExceeded("robots", ROBOT_QUOTA)
                self._conn.execute(
                    """INSERT INTO robot_assets
                       (id, tenant_id, digest, robot_type, data, xml_content, deleted_at)
                       VALUES (?, ?, ?, ?, ?, ?, NULL)""",
                    (
                        robot.id,
                        robot.tenant_id,
                        robot.digest,
                        robot.robot_type,
                        robot.model_dump_json(),
                        xml_content,
                    ),
                )
                self._conn.execute("COMMIT")
                return robot, True
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def list_robots(self, tenant_id: str) -> list[RobotAsset]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT tenant_id, data FROM robot_assets
                   WHERE tenant_id = ? AND deleted_at IS NULL ORDER BY rowid DESC""",
                (tenant_id,),
            ).fetchall()
        return [self._robot(row) for row in rows]

    def get_robot(self, tenant_id: str, robot_id: str) -> RobotAsset | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT tenant_id, data FROM robot_assets
                   WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL""",
                (robot_id, tenant_id),
            ).fetchone()
        return None if row is None else self._robot(row)

    def get_robot_content(self, tenant_id: str, robot_id: str) -> tuple[RobotAsset, str] | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT tenant_id, data, xml_content FROM robot_assets
                   WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL""",
                (robot_id, tenant_id),
            ).fetchone()
        if row is None:
            return None
        return self._robot((row[0], row[1])), row[2]

    def delete_robot(self, tenant_id: str, robot_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                """UPDATE robot_assets SET deleted_at = ?
                   WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL""",
                (time.time(), robot_id, tenant_id),
            )
        return cursor.rowcount == 1

    def create_setup(self, setup: RobotSetup) -> tuple[RobotSetup, bool]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute(
                    """SELECT tenant_id, data FROM robot_setups
                       WHERE tenant_id = ? AND digest = ? AND deleted_at IS NULL""",
                    (setup.tenant_id, setup.digest),
                ).fetchone()
                if existing is not None:
                    self._conn.execute("COMMIT")
                    return self._setup(existing), False
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM robot_setups WHERE tenant_id = ? AND deleted_at IS NULL",
                    (setup.tenant_id,),
                ).fetchone()[0]
                if count >= SETUP_QUOTA:
                    raise QuotaExceeded("setups", SETUP_QUOTA)
                self._conn.execute(
                    """INSERT INTO robot_setups
                       (id, tenant_id, robot_id, digest, data, deleted_at)
                       VALUES (?, ?, ?, ?, ?, NULL)""",
                    (
                        setup.id,
                        setup.tenant_id,
                        setup.robot_id,
                        setup.digest,
                        setup.model_dump_json(),
                    ),
                )
                self._conn.execute("COMMIT")
                return setup, True
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def list_setups(self, tenant_id: str) -> list[RobotSetup]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT tenant_id, data FROM robot_setups
                   WHERE tenant_id = ? AND deleted_at IS NULL ORDER BY rowid DESC""",
                (tenant_id,),
            ).fetchall()
        return [self._setup(row) for row in rows]

    def get_setup(self, tenant_id: str, setup_id: str) -> RobotSetup | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT tenant_id, data FROM robot_setups
                   WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL""",
                (setup_id, tenant_id),
            ).fetchone()
        return None if row is None else self._setup(row)

    def delete_setup(self, tenant_id: str, setup_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                """UPDATE robot_setups SET deleted_at = ?
                   WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL""",
                (time.time(), setup_id, tenant_id),
            )
        return cursor.rowcount == 1


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
