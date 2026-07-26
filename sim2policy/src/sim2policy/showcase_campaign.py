"""Nebius-only, serialized controller for the public showcase campaign.

This controller deliberately does not infer a result from provider logs.  It
stores only reviewed plans and sanitized state, and fails closed until the
implementation gate has durable Nebius attestations.
"""

# ruff: noqa: E501, I001

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sim2policy.execution_location import (
    ExecutionLocationError,
    LocationAttestation,
    require_nebius_execution,
    write_location_attestation,
)
from sim2policy.showcase_matrix import EXAMPLE_ORDER, CampaignMatrix, MatrixError, load_matrix


EXIT_OK = 0
EXIT_ACTIVE = 10
EXIT_REJECTED = 20
EXIT_NEEDS_HUMAN = 30
EXIT_INVARIANT = 40

STATES = frozenset(
    {
        "PLANNED", "PREFLIGHTED", "SUBMITTED", "RUNNING", "FINALIZING", "VERIFIED",
        "ACCEPTED", "REJECTED", "NEEDS_HUMAN", "CLEANED",
    }
)
_TRANSITIONS = {
    "PLANNED": {"PREFLIGHTED", "NEEDS_HUMAN"},
    "PREFLIGHTED": {"SUBMITTED", "NEEDS_HUMAN"},
    "SUBMITTED": {"RUNNING", "FINALIZING", "NEEDS_HUMAN"},
    "RUNNING": {"FINALIZING", "NEEDS_HUMAN"},
    "FINALIZING": {"VERIFIED", "NEEDS_HUMAN"},
    "VERIFIED": {"ACCEPTED", "REJECTED", "NEEDS_HUMAN", "CLEANED"},
    "REJECTED": {"CLEANED", "NEEDS_HUMAN"},
    "ACCEPTED": {"CLEANED"},
    "NEEDS_HUMAN": {"CLEANED"},
    "CLEANED": set(),
}
_CAMPAIGN_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_SECRET_NAMES = re.compile(r"(?i)(secret|token|password|access[_-]?key|bearer)")


class CampaignError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe(value: Any) -> Any:
    """Remove accidental credential-shaped keys from every persisted envelope."""
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items() if not _SECRET_NAMES.search(str(key))}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, str) and ("Bearer " in value or "AKIA" in value):
        return "<redacted>"
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_safe(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CampaignStore:
    def __init__(self, root: Path, campaign_id: str) -> None:
        if not _CAMPAIGN_ID.fullmatch(campaign_id):
            raise CampaignError("campaign ID is invalid")
        self.root = root / campaign_id
        self.campaign_id = campaign_id

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def campaign_path(self) -> Path:
        return self.root / "campaign.json"

    def _write(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as stream:
            json.dump(_safe(value), stream, indent=2, sort_keys=True)
            stream.write("\n")
            temporary = Path(stream.name)
        temporary.replace(path)

    def read(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            raise CampaignError("campaign is not initialized")
        result = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise CampaignError("campaign state is invalid")
        return result

    def write(self, state: dict[str, Any]) -> None:
        self._write(self.state_path, state)

    def journal(self, command: str, before: str | None, after: str, code: int, details: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        entry = _safe(
            {
                "timestamp": _now(), "command": command, "before": before,
                "after": after, "exit_code": code, "evidence_digest": _digest(details),
            }
        )
        with (self.root / "journal.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / "lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise CampaignError("campaign lock is held; refuse concurrent advancement") from exc
        try:
            os.write(descriptor, str(os.getpid()).encode())
            yield
        finally:
            os.close(descriptor)
            lock.unlink(missing_ok=True)


def _envelope(
    state: dict[str, Any], *, code: int, decision: str, reason_code: str, next_command: str
) -> tuple[int, dict[str, Any]]:
    result = {
        "campaign_id": state["campaign_id"],
        "state": state["state"],
        "plan_digest": state.get("plan_digest"),
        "remote_id": state.get("remote_id"),
        "evidence_digest": state.get("evidence_digest"),
        "decision": decision,
        "reason_code": reason_code,
        "cleanup_state": state.get("cleanup_state", "not_started"),
        "next_command": next_command,
    }
    return code, _safe(result)


def initialize(store: CampaignStore, matrix: CampaignMatrix, attestation: LocationAttestation) -> tuple[int, dict[str, Any]]:
    with store.lock():
        if store.state_path.exists():
            existing = store.read()
            if existing.get("matrix_digest") != matrix.digest:
                return _envelope(existing, code=EXIT_INVARIANT, decision="BLOCK", reason_code="MATRIX_DIGEST_MISMATCH", next_command="handoff")
            return _envelope(existing, code=EXIT_OK, decision="ALREADY_INITIALIZED", reason_code="IDEMPOTENT", next_command="preflight")
        state = {
            "schema_version": 1,
            "campaign_id": store.campaign_id,
            "matrix_digest": matrix.digest,
            "state": "PLANNED",
            "created_at": _now(),
            "ordered_examples": list(EXAMPLE_ORDER),
            "attempts": {},
            "location_attestation": attestation.to_dict(),
        }
        store._write(store.campaign_path, {"matrix": matrix.normalized, "matrix_digest": matrix.digest})
        write_location_attestation(store.root / "evidence" / "init-location.json", attestation)
        store.write(state)
        store.journal("init", None, "PLANNED", EXIT_OK, state)
        return _envelope(state, code=EXIT_OK, decision="PLANNED", reason_code="INITIALIZED", next_command="preflight")


def _transition(store: CampaignStore, command: str, target: str, *, details: dict[str, Any], code: int = EXIT_OK) -> dict[str, Any]:
    state = store.read()
    before = state["state"]
    if target != before and target not in _TRANSITIONS.get(before, set()):
        raise CampaignError(f"invalid campaign transition: {before} -> {target}")
    state["state"] = target
    state["updated_at"] = _now()
    state["evidence_digest"] = _digest(details)
    state.update(_safe(details))
    store.write(state)
    store.journal(command, before, target, code, details)
    return state


def plan_attempt(store: CampaignStore, matrix: CampaignMatrix, example: str, seed: int) -> tuple[int, dict[str, Any]]:
    with store.lock():
        state = store.read()
        if state.get("matrix_digest") != matrix.digest:
            return _envelope(state, code=EXIT_INVARIANT, decision="BLOCK", reason_code="MATRIX_DIGEST_MISMATCH", next_command="handoff")
        card = matrix.card(example)
        if seed not in card["seeds"]:
            return _envelope(state, code=EXIT_INVARIANT, decision="BLOCK", reason_code="UNDECLARED_SEED", next_command="status")
        plan = {
            "example": example, "seed": seed, "run_id": f"showcase-{store.campaign_id}-{example}-s{seed}",
            "module": f"sim2policy.hosted_{card['backend']}", "config": card["config"],
            "image_tag": card["image"]["tag_template"], "matrix_digest": matrix.digest,
            "steps": card["base_steps"], "checkpoint_every_steps": card["checkpoint_every_steps"],
            "hardware": card["hardware"], "required_artifacts": ["final_policy", "metrics_json", "video_final", "policy_bundle"],
        }
        digest = _digest(plan)
        plans = store.root / "plans"
        store._write(plans / f"{example}-s{seed}.json", {"plan": plan, "plan_digest": digest})
        state["plan_digest"] = digest
        state["last_plan"] = {"example": example, "seed": seed}
        store.write(state)
        store.journal("plan", state["state"], state["state"], EXIT_OK, plan)
        code, envelope = _envelope(state, code=EXIT_OK, decision="PLAN_READY", reason_code="REVIEW_REQUIRED", next_command="submit --confirm-plan-digest <printed-digest>")
        envelope["plan"] = plan
        return code, envelope


def implementation_gate(store: CampaignStore, matrix: CampaignMatrix) -> tuple[int, dict[str, Any]]:
    """Fail closed until real Nebius build/test/smoke evidence is recorded."""
    with store.lock():
        state = store.read()
        required = [
            "evidence/nebius-quality-gates.json", "evidence/sb3-image.json", "evidence/mjx-image.json",
            "evidence/sb3-smoke.json", "evidence/mjx-smoke.json", "evidence/cloud-audit.json",
        ]
        absent = [item for item in required if not (store.root / item).is_file()]
        if absent:
            state = _transition(store, "implementation-gate", "NEEDS_HUMAN", details={"gate_missing": absent}, code=EXIT_NEEDS_HUMAN)
            return _envelope(state, code=EXIT_NEEDS_HUMAN, decision="BLOCK", reason_code="IMPLEMENTATION_EVIDENCE_MISSING", next_command="handoff")
        state = _transition(store, "implementation-gate", "PREFLIGHTED", details={"implementation_gate": "passed", "matrix_digest": matrix.digest})
        return _envelope(state, code=EXIT_OK, decision="PASS", reason_code="IMPLEMENTATION_COMPLETE", next_command="plan")


def submit(store: CampaignStore, matrix: CampaignMatrix, example: str, seed: int, confirmation: str) -> tuple[int, dict[str, Any]]:
    """Record a reviewed submission intent; provider dispatch is intentionally gated.

    The provider adapter is enabled only after the implementation evidence exists,
    so an agent cannot turn a partially implemented state machine into a paid run.
    """
    with store.lock():
        state = store.read()
        if state.get("state") != "PREFLIGHTED":
            return _envelope(state, code=EXIT_NEEDS_HUMAN, decision="BLOCK", reason_code="PREFLIGHT_REQUIRED", next_command="implementation-gate")
        if confirmation != state.get("plan_digest") or state.get("last_plan") != {"example": example, "seed": seed}:
            return _envelope(state, code=EXIT_INVARIANT, decision="BLOCK", reason_code="PLAN_DIGEST_MISMATCH", next_command="plan")
        return _envelope(state, code=EXIT_NEEDS_HUMAN, decision="BLOCK", reason_code="PROVIDER_ADAPTER_NOT_ATTESTED", next_command="handoff")


def status(store: CampaignStore) -> tuple[int, dict[str, Any]]:
    state = store.read()
    next_command = "handoff" if state["state"] == "NEEDS_HUMAN" else "preflight"
    return _envelope(state, code=EXIT_OK, decision="STATUS", reason_code="STATE_READ", next_command=next_command)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nebius-only curated showcase campaign controller")
    parser.add_argument("command", choices=("init", "status", "plan", "preflight", "implementation-gate", "submit", "watch", "verify", "select", "extend", "accept", "cleanup", "audit-cloud", "handoff"))
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--matrix", default="configs/showcase_training_matrix.yaml")
    parser.add_argument("--state-root", type=Path, default=Path(".showcase-campaigns"))
    parser.add_argument("--example")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--confirm-plan-digest")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--until-terminal", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    try:
        attestation = require_nebius_execution("campaign")
        args = _parser().parse_args(argv)
        matrix = load_matrix(args.matrix)
        store = CampaignStore(args.state_root, args.campaign_id)
        if args.command == "init":
            code, result = initialize(store, matrix, attestation)
        elif args.command == "status":
            code, result = status(store)
        elif args.command == "plan":
            if args.example is None or args.seed is None:
                raise CampaignError("plan requires --example and --seed")
            code, result = plan_attempt(store, matrix, args.example, args.seed)
        elif args.command in {"preflight", "implementation-gate"}:
            code, result = implementation_gate(store, matrix)
        elif args.command == "submit":
            if args.example is None or args.seed is None or args.confirm_plan_digest is None:
                raise CampaignError("submit requires example, seed, and confirmed plan digest")
            code, result = submit(store, matrix, args.example, args.seed, args.confirm_plan_digest)
        else:
            state = store.read()
            code, result = _envelope(state, code=EXIT_NEEDS_HUMAN, decision="BLOCK", reason_code="COMMAND_NOT_IMPLEMENTED", next_command="handoff")
    except (CampaignError, MatrixError, ExecutionLocationError) as exc:
        code, result = EXIT_INVARIANT, {"decision": "BLOCK", "reason_code": str(exc), "next_command": "handoff"}
    print(json.dumps(_safe(result), sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
