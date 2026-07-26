from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Must be set before `app.main` is imported: the stores open the database at import time.
os.environ.setdefault("SAAS_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="saas-test-"), "saas.db"))

from app import main


class RecordingSender:
    """Captures codes instead of logging/sending so tests can log in."""

    name = "recording"

    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send_code(self, email: str, code: str) -> None:
        self.codes[email] = code


@pytest.fixture()
def sender() -> RecordingSender:
    recorder = RecordingSender()
    main._auth.sender = recorder
    return recorder


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main.app)


@pytest.fixture()
def store():
    """A fresh JobStore, which also serves as the showcase manifest cache."""
    from app.store import JobStore

    return JobStore(os.path.join(tempfile.mkdtemp(prefix="saas-store-"), "store.db"))


@pytest.fixture()
def pinned(monkeypatch):
    """Pin `hopper-balance` at the in-memory `gallery-run`, restoring afterwards.

    `SHOWCASE_RUNS` normally holds placeholders that resolve to no run at all, so a
    test that needs a published entry has to pin a real one.
    """
    from app import catalog

    monkeypatch.setitem(catalog.SHOWCASE_RUNS, "hopper-balance", "gallery-run")
    catalog.validate_showcase_runs()
    yield "hopper-balance"
    # The validated map caches the pinned values; rebuild it from the restored dict.
    monkeypatch.undo()
    catalog.validate_showcase_runs()


@pytest.fixture()
def login(client: TestClient, sender: RecordingSender):
    """Log an email in and return auth headers."""

    def _login(email: str) -> dict[str, str]:
        assert client.post("/auth/request-code", json={"email": email}).status_code == 200
        res = client.post("/auth/verify", json={"email": email, "code": sender.codes[email]})
        assert res.status_code == 200
        return {"Authorization": f"Bearer {res.json()['token']}"}

    return _login
