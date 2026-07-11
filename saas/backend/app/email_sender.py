"""Pluggable email delivery for login codes.

Mirrors the orchestration-backend pattern: `mock` (default, credential-free) logs the
code so the flow is demoable locally; `smtp` sends real mail via stdlib smtplib.
"""

from __future__ import annotations

import logging
import os
import smtplib
import socket
import ssl
import time
from dataclasses import dataclass
from email.utils import parseaddr
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger("saas.email")


class EmailSender(Protocol):
    name: str

    def send_code(self, email: str, code: str) -> None: ...


class EmailDeliveryError(Exception):
    """Sanitized delivery failure safe to translate into a retryable API error."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str
    tls_mode: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> SmtpConfig:
        host = os.environ.get("SAAS_SMTP_HOST", "").strip()
        user = os.environ.get("SAAS_SMTP_USER", "").strip()
        password = os.environ.get("SAAS_SMTP_PASSWORD", "")
        sender = os.environ.get("SAAS_SMTP_FROM", "").strip()
        tls_mode = os.environ.get("SAAS_SMTP_TLS_MODE", "starttls").strip().lower()
        port = _positive_number("SAAS_SMTP_PORT", "587", integer=True, maximum=65535)
        timeout = _positive_number("SAAS_SMTP_TIMEOUT_SECONDS", "10", maximum=60)

        missing = [
            name
            for name, value in {
                "SAAS_SMTP_HOST": host,
                "SAAS_SMTP_USER": user,
                "SAAS_SMTP_PASSWORD": password,
                "SAAS_SMTP_FROM": sender,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"missing required SMTP configuration: {', '.join(missing)}")
        if tls_mode not in {"starttls", "ssl"}:
            raise ValueError("SAAS_SMTP_TLS_MODE must be 'starttls' or 'ssl'")
        _, sender_address = parseaddr(sender)
        if not _looks_like_email(sender_address):
            raise ValueError("SAAS_SMTP_FROM must contain a valid email address")
        return cls(host, int(port), user, password, sender, tls_mode, float(timeout))


def _positive_number(name: str, default: str, *, integer: bool = False, maximum: float) -> float:
    raw = os.environ.get(name, default)
    try:
        value = int(raw) if integer else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if value <= 0 or value > maximum:
        raise ValueError(f"{name} must be greater than 0 and at most {maximum:g}")
    return value


def _looks_like_email(value: str) -> bool:
    local, separator, domain = value.rpartition("@")
    return bool(local and separator and "." in domain and not any(c.isspace() for c in value))


class MockEmailSender:
    """Logs the code instead of sending mail. For local/demo use only."""

    name = "mock"

    def send_code(self, email: str, code: str) -> None:
        # WARNING level so the code is visible under the default (uvicorn) log config.
        logger.warning("MOCK EMAIL to %s: your Sim2Policy login code is %s", email, code)


class SmtpEmailSender:
    """Sends the code over SMTP. Credentials come from SAAS_SMTP_* env vars."""

    name = "smtp"

    def __init__(self) -> None:
        self.config = SmtpConfig.from_env()

    def send_code(self, email: str, code: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = "Your Sim2Policy login code"
        msg["From"] = self.config.sender
        msg["To"] = email
        msg.set_content(
            f"Your one-time login code is: {code}\n\n"
            "It expires in 10 minutes. If you did not request it, ignore this email."
        )
        started = time.monotonic()
        try:
            context = ssl.create_default_context()
            if self.config.tls_mode == "ssl":
                client = smtplib.SMTP_SSL(
                    self.config.host,
                    self.config.port,
                    timeout=self.config.timeout_seconds,
                    context=context,
                )
            else:
                client = smtplib.SMTP(
                    self.config.host,
                    self.config.port,
                    timeout=self.config.timeout_seconds,
                )
            with client as smtp:
                if self.config.tls_mode == "starttls":
                    smtp.starttls(context=context)
                smtp.login(self.config.user, self.config.password)
                smtp.send_message(msg)
        except Exception as exc:
            category = _delivery_error_category(exc)
            logger.warning(
                "email_delivery result=failure category=%s latency_ms=%d",
                category,
                int((time.monotonic() - started) * 1000),
            )
            raise EmailDeliveryError(category) from None
        logger.info(
            "email_delivery result=accepted latency_ms=%d",
            int((time.monotonic() - started) * 1000),
        )


def _delivery_error_category(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "authentication"
    if isinstance(exc, (ssl.SSLError, smtplib.SMTPNotSupportedError)):
        return "tls"
    if isinstance(exc, (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused)):
        return "recipient"
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return "connection"
    if isinstance(exc, (smtplib.SMTPDataError, smtplib.SMTPResponseException)):
        return "rejected"
    if isinstance(exc, OSError):
        return "connection"
    return "provider"


def build_email_sender(name: str) -> EmailSender:
    if name == "mock":
        logger.warning(
            "SAAS_EMAIL_BACKEND=mock — login codes are written to the server log. "
            "Do not use this mode for a real deployment."
        )
        return MockEmailSender()
    if name == "smtp":
        return SmtpEmailSender()
    raise ValueError(f"unknown email backend: {name!r}")
