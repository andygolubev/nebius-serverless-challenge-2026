"""Local-only FastAPI server seeded with isolated browser-test sessions.

This is a process harness, not an API backdoor. It refuses to start unless the explicit
local-validation flag is set and always binds to loopback.
"""

from __future__ import annotations

import atexit
import os
import tempfile
import time

if os.environ.get("SAAS_VALIDATION_LOCAL") != "1":
    raise RuntimeError("validation local server requires SAAS_VALIDATION_LOCAL=1")

_temporary_database = tempfile.TemporaryDirectory(prefix="saas-form-validation-")
atexit.register(_temporary_database.cleanup)
os.environ["SAAS_DB_PATH"] = f"{_temporary_database.name}/saas.db"
os.environ["SAAS_ORCHESTRATION_BACKEND"] = "mock"
os.environ["SAAS_EMAIL_BACKEND"] = "mock"
os.environ["CUSTOM_ROBOT_TRAINING_ENABLED"] = "true"
os.environ["CUSTOM_ROBOT_MAX_ACTIVE_PREPARATIONS"] = "4"
os.environ["CUSTOM_ROBOT_MAX_ACTIVE_TRAINING_JOBS"] = "4"
os.environ["CUSTOM_ROBOT_MAX_DAILY_STARTS"] = "40"

from app import main  # noqa: E402
from app.store import Session  # noqa: E402

WORKERS = int(os.environ.get("SAAS_VALIDATION_WORKERS", "4"))
SESSION_PREFIX = os.environ.get(
    "SAAS_VALIDATION_SESSION_PREFIX", "form-validation-worker"
)
for worker in range(WORKERS):
    email = f"form-validation-worker-{worker}@example.test"
    token = f"{SESSION_PREFIX}-{worker}"
    main._auth.store.ensure_user(email)
    main._auth.store.put_session(
        Session(token=token, email=email, expires_at=time.time() + 6 * 60 * 60)
    )

app = main.app


def run() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    run()
