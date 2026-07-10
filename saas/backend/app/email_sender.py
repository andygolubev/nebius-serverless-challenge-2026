"""Pluggable email delivery for login codes.

Mirrors the orchestration-backend pattern: `mock` (default, credential-free) logs the
code so the flow is demoable locally; `smtp` sends real mail via stdlib smtplib.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger("saas.email")


class EmailSender(Protocol):
    name: str

    def send_code(self, email: str, code: str) -> None: ...


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
        self.host = os.environ["SAAS_SMTP_HOST"]
        self.port = int(os.environ.get("SAAS_SMTP_PORT", "587"))
        self.user = os.environ.get("SAAS_SMTP_USER", "")
        self.password = os.environ.get("SAAS_SMTP_PASSWORD", "")
        self.sender = os.environ.get("SAAS_SMTP_FROM", self.user)

    def send_code(self, email: str, code: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = "Your Sim2Policy login code"
        msg["From"] = self.sender
        msg["To"] = email
        msg.set_content(
            f"Your one-time login code is: {code}\n\n"
            "It expires in 10 minutes. If you did not request it, ignore this email."
        )
        with smtplib.SMTP(self.host, self.port) as smtp:
            smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)


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
