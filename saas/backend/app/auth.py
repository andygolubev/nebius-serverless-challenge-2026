"""Passwordless email + one-time-code auth.

Codes are 6-digit, stored as SHA-256 hashes, expire after 10 minutes, are single-use,
and die after 5 failed attempts. Sessions are opaque server-side tokens (revocable,
no key management) with a TTL from SAAS_SESSION_TTL_HOURS.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time

from .email_sender import EmailSender
from .store import AuthStore, PendingCode, Session

CODE_TTL_SECONDS = 10 * 60
MAX_VERIFY_ATTEMPTS = 5
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 15 * 60

# Pragmatic format check; deliverability is proven by the code round-trip itself.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class RateLimited(Exception):
    pass


class AuthService:
    def __init__(self, store: AuthStore, sender: EmailSender) -> None:
        self.store = store
        self.sender = sender
        self.session_ttl_seconds = float(os.environ.get("SAAS_SESSION_TTL_HOURS", "24")) * 3600

    def request_code(self, email: str) -> None:
        """Generate, store (hashed), and send a one-time code. Raises RateLimited."""
        if not self.store.allow_code_request(email, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS):
            raise RateLimited(email)
        code = f"{secrets.randbelow(10**6):06d}"
        self.store.set_code(
            email,
            PendingCode(code_hash=_hash_code(code), expires_at=time.time() + CODE_TTL_SECONDS),
        )
        self.sender.send_code(email, code)

    def verify_code(self, email: str, code: str) -> str | None:
        """Exchange a valid code for a session token; None on any failure."""
        pending = self.store.get_code(email)
        if pending is None or pending.expires_at < time.time():
            self.store.delete_code(email)
            return None
        if self.store.bump_attempts(email) > MAX_VERIFY_ATTEMPTS:
            self.store.delete_code(email)
            return None
        if not secrets.compare_digest(pending.code_hash, _hash_code(code)):
            return None
        self.store.delete_code(email)  # single-use
        self.store.ensure_user(email)
        session = Session(
            token=secrets.token_urlsafe(32),
            email=email,
            expires_at=time.time() + self.session_ttl_seconds,
        )
        self.store.put_session(session)
        return session.token

    def resolve_session(self, token: str) -> Session | None:
        return self.store.get_session(token)

    def logout(self, token: str) -> None:
        self.store.delete_session(token)
