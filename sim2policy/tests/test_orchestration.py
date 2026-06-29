from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sim2policy.api.orchestration import (
    MockBackend,
    NebiusBackend,
    OrchestrationError,
    build_backend,
)
from sim2policy.api.presets import PresetCatalog
from sim2policy.config import StorageConfig
from sim2policy.runstate import STATUS_COMPLETED, STATUS_FAILED, RunStateStore

ROOT = Path(__file__).parents[1]
CATALOG = ROOT / "configs" / "training_presets.yaml"


def resolved(preset: str = "ant-demo", **params: Any):
    return PresetCatalog.load(CATALOG).resolve(preset, params)


def state_for(tmp_path: Path, run_id: str = "ant-demo-20260629-aaa111") -> RunStateStore:
    return RunStateStore(StorageConfig(mode="local"), run_id, tmp_path)


def test_build_backend_selects_implementation() -> None:
    assert isinstance(build_backend("mock"), MockBackend)
    with pytest.raises(OrchestrationError):
        build_backend("unknown")


def test_mock_backend_completes_full_lifecycle(tmp_path: Path) -> None:
    state = state_for(tmp_path)
    state.init_status(preset="ant-demo")
    MockBackend(background=False).launch("ant-demo-20260629-aaa111", resolved(), state)

    status = state.read_status()
    assert status.status == STATUS_COMPLETED
    artifacts = state.read_manifest()
    assert "final_policy" in artifacts
    assert "progression_montage" in artifacts  # render_progress_video default True


def test_mock_backend_respects_render_flag(tmp_path: Path) -> None:
    state = state_for(tmp_path)
    state.init_status(preset="ant-demo")
    MockBackend(background=False).launch(
        "ant-demo-20260629-aaa111", resolved(render_progress_video=False), state
    )
    artifacts = state.read_manifest()
    assert "video_final" in artifacts
    assert "progression_montage" not in artifacts


def test_mock_backend_background_can_be_awaited(tmp_path: Path) -> None:
    state = state_for(tmp_path)
    state.init_status(preset="ant-demo")
    backend = MockBackend(background=True)
    backend.launch("ant-demo-20260629-aaa111", resolved(), state)
    backend.wait("ant-demo-20260629-aaa111", timeout=5)
    assert state.read_status().status == STATUS_COMPLETED


def test_nebius_backend_submits_via_script(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_runner(cmd, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]

        class Result:
            stdout = "job-id-123"

        return Result()

    state = state_for(tmp_path)
    state.init_status(preset="ant-demo")
    backend = NebiusBackend(
        submit_script="jobs/submit.sh",
        env={
            "IMAGE": "sim2policy:sb3",
            "PLATFORM": "gpu-l40s-a",
            "PRESET": "1gpu-8vcpu-32gb",
            "SUBNET_ID": "subnet-123",
            "DRY_RUN": "1",
        },
        runner=fake_runner,
    )
    handle = backend.launch("ant-demo-20260629-aaa111", resolved(), state)

    assert handle["job_handle"] == "job-id-123"
    assert captured["cmd"] == ["jobs/submit.sh"]
    # only run_id + resolved config cross the boundary
    assert captured["env"]["RUN_ID"] == "ant-demo-20260629-aaa111"
    assert captured["env"]["CONFIG"] == "configs/ant_sb3.yaml"
    assert captured["env"]["BACKEND"] == "sb3"
    assert captured["env"]["TIMEOUT"] == "3h"
    assert captured["env"]["DRY_RUN"] == "1"


def test_nebius_backend_missing_settings_marks_failed(tmp_path: Path) -> None:
    state = state_for(tmp_path)
    state.init_status(preset="ant-demo")
    backend = NebiusBackend(submit_script="jobs/submit.sh", env={}, runner=lambda *a, **k: None)
    with pytest.raises(OrchestrationError):
        backend.launch("ant-demo-20260629-aaa111", resolved(), state)
    assert state.read_status().status == STATUS_FAILED


def test_nebius_backend_submission_failure_marks_failed(tmp_path: Path) -> None:
    def boom(cmd, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("submit failed")

    state = state_for(tmp_path)
    state.init_status(preset="ant-demo")
    backend = NebiusBackend(
        submit_script="jobs/submit.sh",
        env={
            "IMAGE": "i",
            "PLATFORM": "p",
            "PRESET": "pr",
            "SUBNET_ID": "s",
        },
        runner=boom,
    )
    with pytest.raises(OrchestrationError):
        backend.launch("ant-demo-20260629-aaa111", resolved(), state)
    assert state.read_status().status == STATUS_FAILED
