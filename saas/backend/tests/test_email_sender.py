"""Production SMTP configuration, transport, failure normalization, and log safety."""

from __future__ import annotations

import logging
import smtplib
import ssl

import pytest

from app.email_sender import EmailDeliveryError, SmtpConfig, SmtpEmailSender


SMTP_ENV = {
    "SAAS_SMTP_HOST": "in-v3.mailjet.com",
    "SAAS_SMTP_PORT": "587",
    "SAAS_SMTP_USER": "api-key-marker",
    "SAAS_SMTP_PASSWORD": "secret-key-marker",
    "SAAS_SMTP_FROM": "Sim2Policy <login@sim-policy-trainer-challenge.info>",
    "SAAS_SMTP_TLS_MODE": "starttls",
    "SAAS_SMTP_TIMEOUT_SECONDS": "10",
}


def _set_smtp_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    for key, value in {**SMTP_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SAAS_SMTP_HOST", ""),
        ("SAAS_SMTP_USER", ""),
        ("SAAS_SMTP_PASSWORD", ""),
        ("SAAS_SMTP_FROM", "invalid"),
        ("SAAS_SMTP_PORT", "zero"),
        ("SAAS_SMTP_PORT", "0"),
        ("SAAS_SMTP_TIMEOUT_SECONDS", "61"),
        ("SAAS_SMTP_TLS_MODE", "none"),
    ],
)
def test_smtp_configuration_rejects_invalid_values(monkeypatch, name, value):
    _set_smtp_env(monkeypatch, **{name: value})
    with pytest.raises(ValueError):
        SmtpConfig.from_env()


def test_smtp_configuration_accepts_mailjet_defaults(monkeypatch):
    _set_smtp_env(monkeypatch)
    config = SmtpConfig.from_env()
    assert config.host == "in-v3.mailjet.com"
    assert config.port == 587
    assert config.tls_mode == "starttls"
    assert config.timeout_seconds == 10


class ScriptedSmtp:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.started_tls = False
        self.logged_in = False
        self.message = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self, *, context):
        assert context is not None
        self.started_tls = True

    def login(self, user, password):
        assert user == "api-key-marker"
        assert password == "secret-key-marker"
        self.logged_in = True
        if self.error:
            raise self.error

    def send_message(self, message):
        self.message = message


def test_starttls_delivery_uses_timeout_and_credentials(monkeypatch, caplog):
    _set_smtp_env(monkeypatch)
    scripted = ScriptedSmtp()

    def build_client(host, port, *, timeout):
        assert (host, port, timeout) == ("in-v3.mailjet.com", 587, 10)
        return scripted

    monkeypatch.setattr(smtplib, "SMTP", build_client)
    caplog.set_level(logging.INFO, logger="saas.email")
    SmtpEmailSender().send_code("private-recipient@example.com", "654321")

    assert scripted.started_tls and scripted.logged_in
    assert "654321" in scripted.message.get_content()
    assert "result=accepted" in caplog.text
    assert "private-recipient@example.com" not in caplog.text
    assert "654321" not in caplog.text
    assert "api-key-marker" not in caplog.text
    assert "secret-key-marker" not in caplog.text


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (TimeoutError("private timeout text"), "timeout"),
        (OSError("private host text"), "connection"),
        (ssl.SSLError("private TLS text"), "tls"),
        (smtplib.SMTPAuthenticationError(535, b"private auth text"), "authentication"),
        (smtplib.SMTPRecipientsRefused({"hidden@example.com": (550, b"private recipient text")}), "recipient"),
        (smtplib.SMTPDataError(550, b"private rejection text"), "rejected"),
    ],
)
def test_smtp_failures_are_sanitized(monkeypatch, caplog, error, category):
    _set_smtp_env(monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP", lambda *_args, **_kwargs: ScriptedSmtp(error))
    caplog.set_level(logging.WARNING, logger="saas.email")

    with pytest.raises(EmailDeliveryError) as raised:
        SmtpEmailSender().send_code("private-recipient@example.com", "654321")

    assert raised.value.category == category
    assert f"category={category}" in caplog.text
    for secret in (
        "private-recipient@example.com",
        "654321",
        "api-key-marker",
        "secret-key-marker",
        "private timeout text",
        "private host text",
        "private TLS text",
        "private auth text",
        "private recipient text",
        "hidden@example.com",
        "private rejection text",
    ):
        assert secret not in caplog.text
