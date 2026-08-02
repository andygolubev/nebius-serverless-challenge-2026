"""Local-only FastAPI server seeded with isolated browser-test sessions.

This is a process harness, not an API backdoor. It refuses to start unless the explicit
local-validation flag is set and always binds to loopback.
"""

from __future__ import annotations

import atexit
import os
import tempfile
import time

from fastapi import Depends, HTTPException

if os.environ.get("SAAS_VALIDATION_LOCAL") != "1":
    raise RuntimeError("validation local server requires SAAS_VALIDATION_LOCAL=1")

_temporary_database = tempfile.TemporaryDirectory(prefix="saas-form-validation-")
atexit.register(_temporary_database.cleanup)
os.environ["SAAS_DB_PATH"] = f"{_temporary_database.name}/saas.db"
os.environ["SAAS_ORCHESTRATION_BACKEND"] = "mock"
os.environ["SAAS_EMAIL_BACKEND"] = "mock"
os.environ["CUSTOM_ROBOT_TRAINING_ENABLED"] = "true"
os.environ["CUSTOM_ROBOT_MAX_ACTIVE_PREPARATIONS"] = "1"
os.environ["CUSTOM_ROBOT_MAX_ACTIVE_TRAINING_JOBS"] = "4"
os.environ["CUSTOM_ROBOT_MAX_DAILY_STARTS"] = "40"

from app import main  # noqa: E402
from app.store import Session  # noqa: E402

WORKERS = int(os.environ.get("SAAS_VALIDATION_WORKERS", "8"))
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
_preparation_modes: dict[str, str] = {}
_training_modes: dict[str, str] = {}
_launch_preparation = main._backend.launch_preparation
_launch_training = main._backend.launch


def _controlled_launch_preparation(attempt, store) -> None:
    mode = _preparation_modes.get(attempt.tenant_id, "success")
    if mode == "fail-once":
        _preparation_modes.pop(attempt.tenant_id, None)
        store.put_preparation(
            attempt.model_copy(
                update={
                    "state": "failed",
                    "phase": "render",
                    "failure_phase": "render",
                    "failure_reason": "render-probe-failed",
                    "can_retry": True,
                }
            )
        )
        return
    if mode == "hold":
        store.put_preparation(
            attempt.model_copy(update={"state": "preparing", "phase": "compile"})
        )
        return
    _launch_preparation(attempt, store)


def _controlled_launch_training(job, store) -> None:
    if _training_modes.get(job.tenant_id) == "fail-once":
        _training_modes.pop(job.tenant_id, None)
        store.put(
            job.model_copy(
                update={
                    "status": "failed",
                    "failure_phase": "submission",
                    "error": "mock training submission failed",
                }
            )
        )
        return
    _launch_training(job, store)


main._backend.launch_preparation = _controlled_launch_preparation
main._backend.launch = _controlled_launch_training


@app.post("/_validation/modes")
def set_validation_modes(
    modes: dict[str, str], session: Session = Depends(main.require_session)
) -> dict[str, str]:
    """Select deterministic local-only orchestration outcomes for one test tenant."""

    preparation = modes.get("preparation", "success")
    training = modes.get("training", "success")
    if preparation not in {"success", "fail-once", "hold"}:
        raise HTTPException(status_code=422, detail="invalid preparation mode")
    if training not in {"success", "fail-once"}:
        raise HTTPException(status_code=422, detail="invalid training mode")
    _preparation_modes[session.email] = preparation
    _training_modes[session.email] = training
    return {"preparation": preparation, "training": training}


# The production app ends with an SPA catch-all route. Keep local-only harness
# controls ahead of it so Starlette does not resolve POSTs as a 405 partial
# match on the GET-only catch-all.
app.router.routes.insert(0, app.router.routes.pop())


@app.post("/_validation/robot-setups/{setup_id}/stale-preparation")
def stale_validation_preparation(
    setup_id: str, session: Session = Depends(main.require_session)
) -> dict[str, str]:
    """Make one accepted local preparation stale without changing global settings."""

    setup = main._robot_store.get_setup(session.email, setup_id)
    if setup is None:
        raise HTTPException(status_code=404, detail="setup not found")
    attempt = main._custom_store.latest_preparation(session.email, setup_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="preparation not found")
    stale = attempt.model_copy(update={"fingerprint": "f" * 64})
    # `put_preparation` intentionally cannot change the indexed fingerprint. The
    # local harness updates both representations atomically so the next Prepare
    # request reserves a genuinely new current-fingerprint attempt.
    with main._custom_store._lock:
        main._custom_store._conn.execute(
            """UPDATE preparation_attempts SET fingerprint = ?, data = ?
               WHERE id = ? AND tenant_id = ?""",
            (
                stale.fingerprint,
                main._custom_store._attempt_json(stale),
                stale.id,
                stale.tenant_id,
            ),
        )
    return {"setup_id": setup_id, "state": "stale"}


app.router.routes.insert(0, app.router.routes.pop())


def run() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    run()
