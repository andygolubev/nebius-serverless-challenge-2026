"""In-memory, tenant-scoped job + artifact store for the mock stage.

A real backend swaps this for the durable S3 run tree; the interface stays the same.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .models import ArtifactManifest, Job


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._artifacts: dict[str, ArtifactManifest] = {}

    def put(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, tenant_id: str, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            # Tenant isolation: never reveal another tenant's job.
            if job is None or job.tenant_id != tenant_id:
                return None
            return job

    def list(self, tenant_id: str) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs.values() if j.tenant_id == tenant_id]

    def set_artifacts(self, manifest: ArtifactManifest) -> None:
        with self._lock:
            self._artifacts[manifest.job_id] = manifest

    def get_artifacts(self, job_id: str) -> ArtifactManifest | None:
        with self._lock:
            return self._artifacts.get(job_id)


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
    created_at: float = field(default_factory=time.time)


class AuthStore:
    """Users, pending codes, sessions, and per-email rate limiting.

    Single-replica: everything lives in-process, same as JobStore.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: dict[str, User] = {}
        self._codes: dict[str, PendingCode] = {}
        self._sessions: dict[str, Session] = {}
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
            user = self._users.get(email)
            if user is None:
                user = User(email=email)
                self._users[email] = user
            return user

    # -- sessions --

    def put_session(self, session: Session) -> None:
        with self._lock:
            self._sessions[session.token] = session

    def get_session(self, token: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.expires_at < time.time():
                del self._sessions[token]
                return None
            return session

    def delete_session(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)
