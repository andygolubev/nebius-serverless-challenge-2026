"""Auth flow: code request/verify, expiry, attempt limits, sessions, tenant isolation."""

from __future__ import annotations

import time
import uuid

from app import main
from app.email_sender import EmailDeliveryError


def _email() -> str:
    return f"{uuid.uuid4().hex[:10]}@nebius.com"


def test_request_and_verify_happy_path(client, sender):
    email = _email()
    res = client.post("/auth/request-code", json={"email": email})
    assert res.status_code == 200
    assert "code" not in res.text.lower() or sender.codes[email] not in res.text

    res = client.post("/auth/verify", json={"email": email, "code": sender.codes[email]})
    assert res.status_code == 200
    token = res.json()["token"]

    res = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == {"email": email}


def test_invalid_email_format(client, sender):
    res = client.post("/auth/request-code", json={"email": "not-an-email"})
    assert res.status_code == 422


def test_non_nebius_email_rejected(client, sender):
    res = client.post("/auth/request-code", json={"email": "someone@example.com"})
    assert res.status_code == 403


def test_wrong_code_rejected(client, sender):
    email = _email()
    client.post("/auth/request-code", json={"email": email})
    res = client.post("/auth/verify", json={"email": email, "code": "000000"})
    if sender.codes[email] == "000000":  # astronomically unlikely, but be exact
        return
    assert res.status_code == 401


def test_expired_code_rejected(client, sender):
    email = _email()
    client.post("/auth/request-code", json={"email": email})
    pending = main._auth.store.get_code(email)
    pending.expires_at = time.time() - 1
    res = client.post("/auth/verify", json={"email": email, "code": sender.codes[email]})
    assert res.status_code == 401


def test_code_is_single_use(client, sender, login):
    email = _email()
    login(email)
    res = client.post("/auth/verify", json={"email": email, "code": sender.codes[email]})
    assert res.status_code == 401


def test_attempt_limit_invalidates_code(client, sender):
    email = _email()
    client.post("/auth/request-code", json={"email": email})
    real = sender.codes[email]
    wrong = "000000" if real != "000000" else "111111"
    for _ in range(5):
        assert client.post("/auth/verify", json={"email": email, "code": wrong}).status_code == 401
    # 6th attempt with the CORRECT code still fails: code invalidated.
    res = client.post("/auth/verify", json={"email": email, "code": real})
    assert res.status_code == 401


def test_rate_limit_code_requests(client, sender):
    email = _email()
    for _ in range(5):
        assert client.post("/auth/request-code", json={"email": email}).status_code == 200
    res = client.post("/auth/request-code", json={"email": email})
    assert res.status_code == 429


class FailingSender:
    name = "smtp"

    def send_code(self, _email: str, _code: str) -> None:
        raise EmailDeliveryError("connection")


def test_delivery_failure_is_retryable_and_code_is_deleted(client):
    email = _email()
    main._auth.sender = FailingSender()
    res = client.post("/auth/request-code", json={"email": email})

    assert res.status_code == 503
    assert res.headers["Retry-After"] == "60"
    assert res.json() == {"detail": "email delivery temporarily unavailable; try again later"}
    assert main._auth.store.get_code(email) is None
    assert client.post("/auth/verify", json={"email": email, "code": "000000"}).status_code == 401


def test_delivery_failures_remain_rate_limited(client):
    email = _email()
    main._auth.sender = FailingSender()
    for _ in range(5):
        assert client.post("/auth/request-code", json={"email": email}).status_code == 503
    assert client.post("/auth/request-code", json={"email": email}).status_code == 429


def test_missing_and_invalid_token_rejected(client):
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/jobs", headers={"X-Tenant-Id": "demo"}).status_code == 401


def test_expired_session_rejected(client, sender, login):
    email = _email()
    headers = login(email)
    token = headers["Authorization"].split(" ")[1]
    session = main._auth.store.get_session(token)
    session.expires_at = time.time() - 1
    main._auth.store.put_session(session)  # write back: sessions are durable, not shared objects
    assert client.get("/jobs", headers=headers).status_code == 401


def test_logout_revokes_session(client, sender, login):
    headers = login(_email())
    assert client.get("/jobs", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/jobs", headers=headers).status_code == 401


def test_tenant_isolation(client, sender, login):
    alice, bob = login(_email()), login(_email())
    res = client.post("/jobs", json={"preset": "go1-mjx-quick"}, headers=alice)
    assert res.status_code == 201
    job_id = res.json()["id"]
    assert client.get(f"/jobs/{job_id}", headers=alice).status_code == 200
    assert client.get(f"/jobs/{job_id}", headers=bob).status_code == 404
    assert all(j["id"] != job_id for j in client.get("/jobs", headers=bob).json())
