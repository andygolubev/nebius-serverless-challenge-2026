"""SQLite-backed, tenant-scoped stores for users, sessions, jobs, and artifacts.

Durable state (users, sessions, jobs, artifact manifests) lives in the SQLite file from
SAAS_DB_PATH so it survives restarts and redeploys. Pending one-time codes and rate-limit
windows stay in process memory: they live minutes by design and are safe to lose.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass

from . import db
from .analytics import daily_rollup_and_prune
from .models import (
    TERMINAL_STATES,
    ArtifactManifest,
    Job,
    PreparationAttempt,
    RobotAsset,
    RobotSetup,
)

ROBOT_QUOTA = 20
SETUP_QUOTA = 50


class _SQLiteStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._conn = db.connect(db_path)


class AnalyticsStore(_SQLiteStore):
    """Anonymous analytics only; deliberately has no tenant or session operations."""

    def __init__(self, db_path: str | None = None, *, session_gap_minutes: int = 30) -> None:
        super().__init__(db_path)
        self._session_gap_seconds = session_gap_minutes * 60

    def record(
        self,
        visit_id: str | None,
        view: str,
        entity_id: str | None,
        ip_hash: str,
        user_agent: str,
        referrer: str,
        is_bot: bool,
        now: float,
    ) -> str:
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            row = (
                self._conn.execute(
                    "SELECT last_seen, ip_hash, user_agent FROM analytics_visits WHERE id = ?",
                    (visit_id,),
                ).fetchone()
                if visit_id
                else None
            )
            reusable = row is not None and (
                now - row[0] <= self._session_gap_seconds
                and row[1] == ip_hash
                and row[2] == user_agent
            )
            # The browser mints its per-tab UUID. It becomes the persisted visit
            # ID on first sight; a stale or forged existing ID is replaced.
            actual_visit_id = (
                visit_id if visit_id and (reusable or row is None) else str(uuid.uuid4())
            )
            if reusable:
                self._conn.execute(
                    "UPDATE analytics_visits SET last_seen = ? WHERE id = ?",
                    (now, actual_visit_id),
                )
            else:
                self._conn.execute(
                    """INSERT INTO analytics_visits
                       (id, first_seen, last_seen, ip_hash, user_agent, referrer, is_bot)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (actual_visit_id, now, now, ip_hash, user_agent, referrer, int(is_bot)),
                )
            self._conn.execute(
                """INSERT INTO analytics_page_views (visit_id, view, entity_id, created_at)
                   VALUES (?, ?, ?, ?)""",
                (actual_visit_id, view, entity_id, now),
            )
            return actual_visit_id

    def prune(self, retention_days: int, now: float) -> None:
        with self._lock:
            daily_rollup_and_prune(self._conn, retention_days, now)


class QuotaExceeded(Exception):
    def __init__(self, field: str, limit: int) -> None:
        self.field = field
        self.limit = limit
        super().__init__(f"{field} quota of {limit} reached")


class JobStore(_SQLiteStore):
    """Append/update-only job history.

    Terminal jobs and artifact manifests are intentionally retained. There is
    no delete operation: provider-resource lifecycle must never erase the
    tenant-visible history kept in SQLite and object storage.
    """

    def put(self, job: Job) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO jobs
                   (id, tenant_id, gallery_example_id, data) VALUES (?, ?, ?, ?)""",
                (
                    job.id,
                    job.tenant_id,
                    job.gallery_example_id,
                    job.model_dump_json(),
                ),
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


class CustomTrainingStore(_SQLiteStore):
    """Atomic preparation and setup-bound custom start reservations."""

    @staticmethod
    def _attempt(row: tuple[str, str]) -> PreparationAttempt:
        return PreparationAttempt.model_validate_json(row[1]).model_copy(
            update={"tenant_id": row[0]}
        )

    @staticmethod
    def _attempt_json(attempt: PreparationAttempt) -> str:
        """Persist private authorities even though API serialization excludes them."""
        payload = attempt.model_dump(mode="json")
        for field in (
            "input_manifest_key",
            "input_manifest_sha256",
            "report_key",
            "nebius_job_id",
        ):
            payload[field] = getattr(attempt, field)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def latest_preparation(
        self, tenant_id: str, setup_id: str
    ) -> PreparationAttempt | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT tenant_id, data FROM preparation_attempts
                   WHERE tenant_id = ? AND setup_id = ?
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (tenant_id, setup_id),
            ).fetchone()
        return None if row is None else self._attempt(row)

    def accepted_preparation(
        self, tenant_id: str, setup_id: str, fingerprint: str
    ) -> PreparationAttempt | None:
        """The accepted preparation for one exact fingerprint, newest first.

        Training asks this rather than ``latest_preparation`` because "latest" and "the
        one that matches" stop being the same row the moment a contract is rolled back.
        ``reserve_preparation`` reuses an existing accepted attempt instead of inserting a
        new one, so re-preparing after a rollback returns the older row and leaves the
        superseded attempt newest -- and a start gated on the newest row then refuses
        forever, with the UI reporting a setup that is prepared and ready.
        """
        with self._lock:
            row = self._conn.execute(
                """SELECT tenant_id, data FROM preparation_attempts
                   WHERE tenant_id = ? AND setup_id = ? AND fingerprint = ?
                     AND json_extract(data, '$.state') = 'accepted'
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (tenant_id, setup_id, fingerprint),
            ).fetchone()
        return None if row is None else self._attempt(row)

    def get_preparation(
        self, tenant_id: str, preparation_id: str
    ) -> PreparationAttempt | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT tenant_id, data FROM preparation_attempts
                   WHERE tenant_id = ? AND id = ?""",
                (tenant_id, preparation_id),
            ).fetchone()
        return None if row is None else self._attempt(row)

    def list_active_preparations(self) -> list[PreparationAttempt]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT tenant_id, data FROM preparation_attempts
                   WHERE state IN ('queued', 'preparing')"""
            ).fetchall()
        return [self._attempt(row) for row in rows]

    def reserve_preparation(
        self,
        attempt: PreparationAttempt,
        *,
        max_active_per_tenant: int,
        retry: bool,
    ) -> tuple[PreparationAttempt, bool]:
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            rows = self._conn.execute(
                """SELECT tenant_id, data FROM preparation_attempts
                   WHERE tenant_id = ? AND setup_id = ? AND fingerprint = ?
                   ORDER BY created_at DESC, rowid DESC""",
                (attempt.tenant_id, attempt.setup_id, attempt.fingerprint),
            ).fetchall()
            existing = [self._attempt(row) for row in rows]
            reusable = next(
                (
                    item
                    for item in existing
                    if item.state in {"queued", "preparing", "accepted"}
                ),
                None,
            )
            if reusable is not None:
                return reusable, False
            if existing and not retry:
                return existing[0], False
            active = self._conn.execute(
                """SELECT COUNT(*) FROM preparation_attempts
                   WHERE tenant_id = ? AND state IN ('queued', 'preparing')""",
                (attempt.tenant_id,),
            ).fetchone()[0]
            if active >= max_active_per_tenant:
                raise QuotaExceeded("active_preparations", max_active_per_tenant)
            self._conn.execute(
                """INSERT INTO preparation_attempts
                   (id, tenant_id, setup_id, robot_id, fingerprint, state, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt.id,
                    attempt.tenant_id,
                    attempt.setup_id,
                    attempt.robot_id,
                    attempt.fingerprint,
                    attempt.state,
                    self._attempt_json(attempt),
                    time.time(),
                ),
            )
            return attempt, True

    def put_preparation(self, attempt: PreparationAttempt) -> None:
        with self._lock:
            cursor = self._conn.execute(
                """UPDATE preparation_attempts SET state = ?, data = ?
                   WHERE id = ? AND tenant_id = ?""",
                (
                    attempt.state,
                    self._attempt_json(attempt),
                    attempt.id,
                    attempt.tenant_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError("preparation attempt does not exist")

    def reserve_training_job(
        self,
        job: Job,
        *,
        setup_id: str,
        idempotency_key: str,
        max_active_per_tenant: int,
        max_daily_starts: int,
    ) -> tuple[Job, bool]:
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self._conn.execute(
                """SELECT job_id FROM custom_training_requests
                   WHERE tenant_id = ? AND setup_id = ? AND idempotency_key = ?""",
                (job.tenant_id, setup_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                row = self._conn.execute(
                    "SELECT data FROM jobs WHERE id = ? AND tenant_id = ?",
                    (existing[0], job.tenant_id),
                ).fetchone()
                if row is None:
                    raise RuntimeError("idempotency reservation has no job")
                return Job.model_validate_json(row[0]), False
            active_jobs = [
                Job.model_validate_json(row[0])
                for row in self._conn.execute(
                    "SELECT data FROM jobs WHERE tenant_id = ?",
                    (job.tenant_id,),
                ).fetchall()
            ]
            active = sum(
                item.job_kind == "custom-robot" and item.status not in TERMINAL_STATES
                for item in active_jobs
            )
            if active >= max_active_per_tenant:
                raise QuotaExceeded("active_training_jobs", max_active_per_tenant)
            since = time.time() - 24 * 60 * 60
            daily = self._conn.execute(
                """SELECT COUNT(*) FROM custom_training_requests
                   WHERE tenant_id = ? AND created_at >= ?""",
                (job.tenant_id, since),
            ).fetchone()[0]
            if daily >= max_daily_starts:
                raise QuotaExceeded("daily_training_starts", max_daily_starts)
            self._conn.execute(
                """INSERT INTO jobs
                   (id, tenant_id, gallery_example_id, data) VALUES (?, ?, ?, ?)""",
                (job.id, job.tenant_id, None, job.model_dump_json()),
            )
            self._conn.execute(
                """INSERT INTO custom_training_requests
                   (tenant_id, setup_id, idempotency_key, job_id, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (job.tenant_id, setup_id, idempotency_key, job.id, time.time()),
            )
            return job, True


class RobotStore(_SQLiteStore):
    """Transactional, tenant-scoped storage for immutable robots and setup drafts."""

    @staticmethod
    def _robot(row: tuple[str, str]) -> RobotAsset:
        return RobotAsset.model_validate_json(row[1]).model_copy(
            update={"tenant_id": row[0]}
        )

    @staticmethod
    def _setup(row: tuple[str, str]) -> RobotSetup:
        return RobotSetup.model_validate_json(row[1]).model_copy(
            update={"tenant_id": row[0]}
        )

    def create_robot(
        self, robot: RobotAsset, xml_content: str
    ) -> tuple[RobotAsset, bool]:
        """Create once, or return the active same-tenant/type/content version."""
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self._conn.execute(
                """SELECT tenant_id, data FROM robot_assets
                   WHERE tenant_id = ? AND robot_type = ? AND digest = ?
                     AND deleted_at IS NULL""",
                (robot.tenant_id, robot.robot_type, robot.digest),
            ).fetchone()
            if existing is not None:
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
            return robot, True

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

    def get_robot_content(
        self, tenant_id: str, robot_id: str, *, include_deleted: bool = False
    ) -> tuple[RobotAsset, str] | None:
        with self._lock:
            query = """SELECT tenant_id, data, xml_content FROM robot_assets
                       WHERE id = ? AND tenant_id = ?"""
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            row = self._conn.execute(query, (robot_id, tenant_id)).fetchone()
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
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self._conn.execute(
                """SELECT tenant_id, data FROM robot_setups
                   WHERE tenant_id = ? AND digest = ? AND deleted_at IS NULL""",
                (setup.tenant_id, setup.digest),
            ).fetchone()
            if existing is not None:
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
            return setup, True

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

    def get_setup_history(self, tenant_id: str, setup_id: str) -> RobotSetup | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT tenant_id, data FROM robot_setups
                   WHERE id = ? AND tenant_id = ?""",
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


class AuthStore(_SQLiteStore):
    """Users and sessions in SQLite; pending codes and rate limiting in memory.

    Single-replica: one process owns the database file, same as JobStore.
    """

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(db_path)
        self._codes: dict[str, PendingCode] = {}
        self._request_times: dict[str, list[float]] = {}

    # -- rate limiting (sliding window) --

    def allow_code_request(self, email: str, limit: int, window_seconds: float) -> bool:
        now = time.time()
        with self._lock:
            times = [
                t
                for t in self._request_times.get(email, [])
                if now - t < window_seconds
            ]
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
                "SELECT token, email, expires_at FROM sessions WHERE token = ?",
                (token,),
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
