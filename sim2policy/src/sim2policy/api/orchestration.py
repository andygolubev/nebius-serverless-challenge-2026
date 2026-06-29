"""Orchestration backends that launch a training run for a resolved preset.

The API never trains; it hands a validated ``run_id`` and a catalog-resolved
configuration to one of these backends:

* :class:`MockBackend` simulates the full lifecycle locally (no Nebius, no GPU)
  so the entire API surface can be exercised in tests and local demos.
* :class:`NebiusBackend` launches a Nebius Serverless AI Job via the existing
  ``jobs/submit.sh`` wrapper.

Only the ``run_id`` and the resolved configuration cross this boundary -- never
user-supplied images, commands, environment IDs, or code.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from sim2policy.api.presets import ResolvedRun
from sim2policy.config import validate_run_id
from sim2policy.runstate import (
    ARTIFACT_KEYS,
    STATUS_COMPLETED,
    STATUS_EVALUATING,
    STATUS_FAILED,
    STATUS_RENDERING,
    STATUS_STARTING,
    STATUS_TRAINING,
    RunStateStore,
)


class OrchestrationError(RuntimeError):
    """Raised when a run cannot be launched."""


class OrchestrationBackend(Protocol):
    name: str

    def launch(
        self, run_id: str, resolved: ResolvedRun, state: RunStateStore
    ) -> dict[str, Any]: ...


def _guard(run_id: str, resolved: ResolvedRun) -> None:
    validate_run_id(run_id)
    preset_config = resolved.config
    if preset_config.training.total_steps <= 0:
        raise OrchestrationError("resolved config has non-positive training steps")


class MockBackend:
    """Simulate a run end-to-end without Nebius or GPU.

    Writes the same object-storage layout (status transitions, placeholder
    artifacts, and a manifest) a real run would produce.
    """

    name = "mock"

    def __init__(self, *, background: bool = False, delay: float = 0.0) -> None:
        self.background = background
        self.delay = delay
        self._threads: dict[str, threading.Thread] = {}

    def launch(
        self, run_id: str, resolved: ResolvedRun, state: RunStateStore
    ) -> dict[str, Any]:
        _guard(run_id, resolved)
        if self.background:
            thread = threading.Thread(
                target=self._simulate, args=(run_id, resolved, state), daemon=True
            )
            self._threads[run_id] = thread
            thread.start()
        else:
            self._simulate(run_id, resolved, state)
        return {"backend": self.name, "run_id": run_id}

    def wait(self, run_id: str, timeout: float | None = None) -> None:
        thread = self._threads.get(run_id)
        if thread is not None:
            thread.join(timeout)

    def _sleep(self) -> None:
        if self.delay:
            import time

            time.sleep(self.delay)

    def _simulate(self, run_id: str, resolved: ResolvedRun, state: RunStateStore) -> None:
        try:
            state.update_status(STATUS_STARTING)
            self._sleep()
            state.update_status(
                STATUS_TRAINING,
                progress={
                    "backend": resolved.backend,
                    "environment": resolved.config.environment,
                    "total_steps": resolved.config.training.total_steps,
                },
            )
            self._sleep()
            render = bool(resolved.safe_params.get("render_progress_video", True))
            self._write_placeholder_artifacts(state, render=render)
            state.update_status(
                STATUS_RENDERING, progress={"latest_checkpoint": "final.zip"}
            )
            self._sleep()
            state.update_status(
                STATUS_EVALUATING, progress={"latest_mean_reward": 1234.5}
            )
            self._sleep()
            state.write_manifest(state.discover_artifacts())
            state.update_status(
                STATUS_COMPLETED, progress={"latest_mean_reward": 1234.5}
            )
        except Exception as exc:  # mock must always leave a terminal state
            state.update_status(STATUS_FAILED, error=f"mock backend error: {exc}")

    def _write_placeholder_artifacts(self, state: RunStateStore, *, render: bool) -> None:
        produced = ["final_policy", "metrics_json", "report_md", "video_final"]
        if render:
            produced += ["video_untrained", "video_mid", "progression_montage"]
        for name in produced:
            key = ARTIFACT_KEYS[name]
            path = state.run_root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            if name == "metrics_json":
                path.write_text(
                    json.dumps(
                        {"mock": True, "mean_reward": 1234.5, "success": True}, indent=2
                    )
                    + "\n",
                    encoding="utf-8",
                )
            elif name == "report_md":
                path.write_text(
                    f"# Sim2Policy mock run\n\nPreset run `{state.run_id}` (mock backend).\n",
                    encoding="utf-8",
                )
            else:
                path.write_bytes(b"sim2policy-mock-artifact")


class NebiusBackend:
    """Launch a Nebius Serverless AI Job via ``jobs/submit.sh``.

    Compute settings (image, platform, hardware preset, subnet) come from the
    deployment environment, never from request input. The training preset only
    contributes the run config path, backend, and duration limit.
    """

    name = "nebius"

    #: Environment variables that configure the Nebius compute target.
    REQUIRED_ENV = ("IMAGE", "PLATFORM", "PRESET", "SUBNET_ID")

    def __init__(
        self,
        *,
        submit_script: str | Path,
        env: dict[str, str] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.submit_script = Path(submit_script)
        self.env = dict(env if env is not None else os.environ)
        self.runner = runner

    def launch(
        self, run_id: str, resolved: ResolvedRun, state: RunStateStore
    ) -> dict[str, Any]:
        _guard(run_id, resolved)
        missing = [name for name in self.REQUIRED_ENV if not self.env.get(name)]
        if missing:
            state.update_status(
                STATUS_FAILED, error=f"missing Nebius settings: {', '.join(missing)}"
            )
            raise OrchestrationError(f"missing Nebius settings: {', '.join(missing)}")

        # CONFIG is the preset's base config path baked into the image; an explicit
        # deployment CONFIG override wins. Compute settings come from the environment.
        job_env = dict(self.env)
        job_env.update(
            {
                "RUN_ID": run_id,
                "CONFIG": self.env.get("CONFIG") or resolved.config_path,
                "BACKEND": resolved.backend,
                "TIMEOUT": resolved.max_duration,
            }
        )

        state.update_status(STATUS_STARTING, progress={"job": "submitting"})
        try:
            result = self.runner(
                [str(self.submit_script)],
                env=job_env,
                check=True,
                text=True,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            detail = getattr(exc, "stderr", None) or str(exc)
            state.update_status(STATUS_FAILED, error=f"job submission failed: {detail}")
            raise OrchestrationError(f"job submission failed: {detail}") from exc

        handle = (result.stdout or "").strip()
        state.update_status(
            STATUS_STARTING, progress={"job": "submitted", "job_handle": handle}
        )
        return {"backend": self.name, "run_id": run_id, "job_handle": handle}


def build_backend(
    backend: str,
    *,
    submit_script: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> OrchestrationBackend:
    if backend == "mock":
        return MockBackend(background=True)
    if backend == "nebius":
        if submit_script is None:
            raise OrchestrationError("nebius backend requires a submit script path")
        return NebiusBackend(submit_script=submit_script, env=env)
    raise OrchestrationError(f"unknown orchestration backend: {backend}")
