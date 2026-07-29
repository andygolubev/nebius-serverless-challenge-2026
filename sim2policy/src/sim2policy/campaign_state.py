"""Durable, non-secret campaign state: atomic writes, one lock, validated transitions.

The campaign survives an interrupted agent, a dropped SSH session, and a rebooted
orchestration VM, so state is the source of truth and memory is not. Three
properties make resume safe:

* **Atomic**: every write lands via a same-directory temporary file plus `replace`,
  so a crash mid-write leaves the previous complete state, never a partial one.
* **Serialized**: one exclusive lock per campaign, taken with `O_EXCL`. It fails
  immediately rather than waiting, because a second operator advancing the same
  campaign is a mistake to report, not a queue to join.
* **Journalled**: an append-only JSONL record of every transition, so the sequence
  that produced the current state is reconstructable after the fact.

Nothing here talks to a provider. Persisting state and calling a cloud API are kept
apart so that a state transition can be tested exhaustively without a network.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import socket
import tempfile
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sim2policy.campaign_redaction import environment_secret_values, redact

# Per-attempt lifecycle. `CLEANED` is terminal: an attempt that has been cleaned up
# is closed, and further work happens under a new attempt.
STATES = (
    "PLANNED",
    "PREFLIGHTED",
    "SUBMITTED",
    "RUNNING",
    "FINALIZING",
    "VERIFIED",
    "ACCEPTED",
    "REJECTED",
    "NEEDS_HUMAN",
    "CLEANED",
)

TRANSITIONS: dict[str, frozenset[str]] = {
    "PLANNED": frozenset({"PREFLIGHTED", "NEEDS_HUMAN"}),
    "PREFLIGHTED": frozenset({"SUBMITTED", "PLANNED", "NEEDS_HUMAN"}),
    "SUBMITTED": frozenset({"RUNNING", "FINALIZING", "VERIFIED", "NEEDS_HUMAN"}),
    "RUNNING": frozenset({"RUNNING", "FINALIZING", "VERIFIED", "NEEDS_HUMAN"}),
    "FINALIZING": frozenset({"FINALIZING", "VERIFIED", "NEEDS_HUMAN"}),
    "VERIFIED": frozenset({"ACCEPTED", "REJECTED", "NEEDS_HUMAN", "CLEANED"}),
    "ACCEPTED": frozenset({"CLEANED", "NEEDS_HUMAN"}),
    "REJECTED": frozenset({"CLEANED", "NEEDS_HUMAN"}),
    # PLANNED is reachable only for an attempt that never acquired a remote job;
    # the caller proves that before re-planning, so no live job can be orphaned.
    "NEEDS_HUMAN": frozenset({"CLEANED", "PLANNED"}),
    "CLEANED": frozenset(),
}

# Attempt states that hold the single remote-job slot.
ACTIVE_STATES = frozenset({"SUBMITTED", "RUNNING", "FINALIZING"})

CAMPAIGN_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
# A tenant job id is `uuid4().hex`. A campaign run identity must never be mistakable
# for one, because both share the artifact keyspace.
_TENANT_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class CampaignError(RuntimeError):
    """Raised for an invalid campaign identity, transition, or lock condition."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def attempt_key(example: str, seed: int, phase: str) -> str:
    return f"{example}:{seed}:{phase}"


def validate_run_identity(run_id: str) -> str:
    if _TENANT_JOB_ID_RE.fullmatch(run_id):
        raise CampaignError("campaign run identity collides with the tenant job space")
    if "/" in run_id or ".." in run_id.split("."):
        raise CampaignError("campaign run identity must be one safe path segment")
    return run_id


class CampaignStore:
    """Owns `<state-root>/<campaign-id>/` and every write into it."""

    def __init__(
        self,
        root: Path,
        campaign_id: str,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if not CAMPAIGN_ID_RE.fullmatch(campaign_id):
            raise CampaignError("campaign ID must be 3-64 lowercase alphanumeric/dash characters")
        self.campaign_id = campaign_id
        self.root = Path(root) / campaign_id
        self._secrets = environment_secret_values(environment)

    # -- paths ---------------------------------------------------------------

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def campaign_path(self) -> Path:
        return self.root / "campaign.json"

    @property
    def journal_path(self) -> Path:
        return self.root / "journal.jsonl"

    @property
    def lock_path(self) -> Path:
        return self.root / "lock"

    @property
    def handoff_path(self) -> Path:
        return self.root / "handoff.md"

    def evidence_path(self, name: str) -> Path:
        return self.root / "evidence" / name

    def plan_path(self, key: str) -> Path:
        return self.root / "plans" / f"{key.replace(':', '-')}.json"

    def audit_path(self, name: str) -> Path:
        return self.root / "audits" / name

    # -- redaction -----------------------------------------------------------

    def safe(self, value: Any) -> Any:
        """The single redaction entry point every persisted value passes through."""
        return redact(value, extra=self._secrets)

    # -- atomic io -----------------------------------------------------------

    def write_json(self, path: Path, value: Mapping[str, Any]) -> None:
        """Write redacted JSON atomically: temp file in the same directory, then replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.safe(dict(value)), indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8", prefix=".tmp-"
        ) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        temporary.replace(path)

    def read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise CampaignError("campaign state file is not an object")
        return value

    def write_text(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        redacted = self.safe(value)
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8", prefix=".tmp-"
        ) as stream:
            stream.write(redacted if isinstance(redacted, str) else str(redacted))
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        temporary.replace(path)

    # -- state ---------------------------------------------------------------

    def initialized(self) -> bool:
        return self.state_path.is_file()

    def read(self) -> dict[str, Any]:
        state = self.read_json(self.state_path)
        if state is None:
            raise CampaignError("campaign is not initialized")
        return state

    def write(self, state: Mapping[str, Any]) -> None:
        self.write_json(self.state_path, state)

    # -- journal -------------------------------------------------------------

    def journal(self, entry: Mapping[str, Any]) -> None:
        """Append one redacted transition record. Never rewrites earlier lines."""
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(self.safe({"timestamp": utc_now(), **dict(entry)}), sort_keys=True)
        with self.journal_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def journal_entries(self) -> list[dict[str, Any]]:
        if not self.journal_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.journal_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    # -- lock ----------------------------------------------------------------

    @contextlib.contextmanager
    def lock(self, command: str = "unknown") -> Iterator[None]:
        """Exclusive campaign lock. Fails immediately; never waits."""
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            holder = self.lock_holder()
            raise CampaignError(
                "campaign lock is held; refuse concurrent advancement "
                f"(holder pid={holder.get('pid')} host={holder.get('hostname')})"
            ) from exc
        try:
            os.write(
                descriptor,
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "hostname": socket.gethostname(),
                        "command": command,
                        "acquired_at": utc_now(),
                    },
                    sort_keys=True,
                ).encode(),
            )
            os.fsync(descriptor)
            os.close(descriptor)
            yield
        finally:
            with contextlib.suppress(FileNotFoundError):
                self.lock_path.unlink()

    def lock_holder(self) -> dict[str, Any]:
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


def process_is_live(pid: int) -> bool:
    """True when a process with `pid` exists and we may signal it.

    `EPERM` counts as live: the process exists, it simply belongs to another user,
    which is exactly the case where clearing its lock would be unsafe.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def validate_transition(before: str, after: str) -> None:
    if after not in STATES:
        raise CampaignError(f"unknown campaign state: {after}")
    if after == before:
        return
    if after not in TRANSITIONS.get(before, frozenset()):
        raise CampaignError(f"invalid campaign transition: {before} -> {after}")


def active_attempt(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """The single attempt currently holding a remote job, if any.

    The one-active-job invariant is checked by reading state rather than by
    remembering, so it holds across process restarts and operators.
    """
    attempts = state.get("attempts")
    if not isinstance(attempts, dict):
        return None
    for key, attempt in sorted(attempts.items()):
        if isinstance(attempt, dict) and attempt.get("state") in ACTIVE_STATES:
            return {"key": key, **attempt}
    return None
