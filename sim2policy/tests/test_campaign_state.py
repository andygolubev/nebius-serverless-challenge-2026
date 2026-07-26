"""Durability, locking, and transition validity of the campaign state store."""

from __future__ import annotations

# ruff: noqa: E501

import json
import os
from pathlib import Path

import pytest

from sim2policy.campaign_state import (
    CampaignError,
    CampaignStore,
    active_attempt,
    attempt_key,
    process_is_live,
    validate_run_identity,
    validate_transition,
)


def _store(tmp_path: Path) -> CampaignStore:
    return CampaignStore(tmp_path, "gallery-result-20260726")


def test_campaign_id_must_be_a_safe_slug(tmp_path: Path) -> None:
    for invalid in ("", "AB", "Gallery", "x", "../escape", "a" * 100):
        with pytest.raises(CampaignError, match="campaign ID"):
            CampaignStore(tmp_path, invalid)


def test_state_writes_are_atomic_and_leave_no_temporary_behind(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write({"state": "PLANNED"})
    store.write({"state": "PREFLIGHTED"})
    assert json.loads(store.state_path.read_text())["state"] == "PREFLIGHTED"
    # A crash mid-write must not be able to leave a partial file behind as state.
    assert not [item for item in store.root.iterdir() if item.name.startswith(".tmp-")]


def test_journal_is_append_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.journal({"command": "init", "after": "PLANNED"})
    store.journal({"command": "plan", "after": "PLANNED"})
    entries = store.journal_entries()
    assert [item["command"] for item in entries] == ["init", "plan"]
    assert all("timestamp" in item for item in entries)


def test_lock_is_exclusive_and_fails_immediately_rather_than_waiting(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.lock("plan"):
        holder = store.lock_holder()
        assert holder["pid"] == os.getpid()
        assert holder["command"] == "plan"
        with pytest.raises(CampaignError, match="lock is held"):
            with store.lock("submit"):
                raise AssertionError("a second holder must never enter the lock")
    # Released on exit, so the next command proceeds normally.
    with store.lock("submit"):
        pass


def test_lock_is_released_even_when_the_body_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        with store.lock("plan"):
            raise ValueError("boom")
    assert not store.lock_path.exists()


def test_process_liveness_is_conservative() -> None:
    assert process_is_live(os.getpid()) is True
    assert process_is_live(0) is False
    assert process_is_live(-1) is False


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("PLANNED", "PREFLIGHTED"),
        ("PREFLIGHTED", "SUBMITTED"),
        ("SUBMITTED", "RUNNING"),
        ("RUNNING", "FINALIZING"),
        ("FINALIZING", "VERIFIED"),
        ("VERIFIED", "ACCEPTED"),
        ("ACCEPTED", "CLEANED"),
        ("RUNNING", "RUNNING"),
    ],
)
def test_declared_transitions_are_permitted(before: str, after: str) -> None:
    validate_transition(before, after)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("PLANNED", "RUNNING"),
        ("CLEANED", "SUBMITTED"),
        ("VERIFIED", "SUBMITTED"),
        ("ACCEPTED", "REJECTED"),
        ("PLANNED", "NOT_A_STATE"),
    ],
)
def test_undeclared_transitions_are_refused(before: str, after: str) -> None:
    with pytest.raises(CampaignError):
        validate_transition(before, after)


def test_active_attempt_finds_the_single_remote_job_slot_holder() -> None:
    state = {
        "attempts": {
            attempt_key("reacher", 0, "base"): {"state": "CLEANED"},
            attempt_key("reacher", 7, "base"): {"state": "RUNNING"},
            attempt_key("ant", 0, "base"): {"state": "PLANNED"},
        }
    }
    active = active_attempt(state)
    assert active is not None and active["key"] == "reacher:7:base"
    assert active_attempt({"attempts": {}}) is None


def test_run_identity_cannot_be_mistaken_for_a_tenant_job() -> None:
    validate_run_identity("showcase-gallery-result-20260726-reacher-s0")
    with pytest.raises(CampaignError, match="tenant job space"):
        validate_run_identity("0123456789abcdef0123456789abcdef")
    with pytest.raises(CampaignError, match="safe path segment"):
        validate_run_identity("showcase/../escape")
