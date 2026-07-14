from __future__ import annotations

import importlib.util
import json
import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from sim2policy.config import load_config
from sim2policy.evaluate import evaluate
from sim2policy.run import create_run_paths
from sim2policy.train_mjx import (
    _parse_initial_worker_flags,
    _repair_brax_checkpoint_config,
    build_playground_command,
    evaluate_mjx,
    fixed_forward_command_state,
    local_forward_velocity,
    train_mjx,
)

ROOT = Path(__file__).parents[1]


def test_build_playground_command_maps_config_to_explicit_flags(tmp_path: Path) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "training.total_steps": 1024,
            "training.n_envs": 32,
        },
    )
    paths = create_run_paths("mjx-command", tmp_path)
    command = build_playground_command(config, paths)
    assert command[:5] == [
        "train-jax-ppo",
        "--env_name=Go1JoystickFlatTerrain",
        "--impl=jax",
        "--seed=0",
        "--num_timesteps=1024",
    ]
    assert "--num_envs=32" in command
    assert "--logdir=" + str(paths.root / "mjx_logs") in command
    assert "--playground_config_overrides" in command
    assert '{"impl":"jax"}' in command
    assert "--policy_hidden_layer_sizes=512,256,128" in command
    assert "--num_evals=2" in command


def test_build_playground_command_rejects_unknown_hyperparameters(tmp_path: Path) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {"training.hyperparameters": {"impl": "jax", "surprise": 1}},
    )
    paths = create_run_paths("mjx-bad-command", tmp_path)
    with pytest.raises(RuntimeError, match="unsupported MJX hyperparameter"):
        build_playground_command(config, paths)


def test_initial_worker_parses_playground_impl_before_config_access() -> None:
    config = load_config(ROOT / "configs/go1_mjx.yaml")

    class FlagValues:
        parsed = False
        argv: list[str] | None = None

        def is_parsed(self) -> bool:
            return self.parsed

        def __call__(self, argv: list[str]) -> None:
            self.argv = argv
            self.parsed = True

    flags = FlagValues()
    _parse_initial_worker_flags(flags, config)
    assert flags.argv == ["sim2policy-mjx-initial", "--impl=jax"]

    _parse_initial_worker_flags(flags, config)
    assert flags.argv == ["sim2policy-mjx-initial", "--impl=jax"]


def test_repair_brax_checkpoint_config_removes_null_initializers(tmp_path: Path) -> None:
    config_path = tmp_path / "ppo_network_config.json"
    config_path.write_text(
        '{"network_factory_kwargs":{"policy_network_kernel_init_fn":null,'
        '"value_network_kernel_init_fn":null,"activation":"swish"}}',
        encoding="utf-8",
    )

    _repair_brax_checkpoint_config(tmp_path)

    repaired = json.loads(config_path.read_text(encoding="utf-8"))
    assert repaired["network_factory_kwargs"] == {"activation": "swish"}


def test_train_mjx_archives_latest_raw_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "training.total_steps": 128,
            "training.n_envs": 4,
            "storage.mode": "local",
        },
    )

    monkeypatch.setattr(
        "sim2policy.train_mjx.validate_mjx_environment",
        lambda config: {"environment": config.environment, "impl": "jax"},
    )

    checkpoint = train_mjx(config, "mjx-run", tmp_path, runner=_fake_checkpoint_runner("64", "128"))
    assert (tmp_path / "mjx-run/checkpoints/initial-000000000000.zip").is_file()
    assert (tmp_path / "mjx-run/checkpoints/step-000000000064.zip").is_file()
    assert checkpoint.name == "final-000000000128.zip"
    assert checkpoint.is_file()
    assert checkpoint.with_suffix(".zip.json").is_file()
    runtime = json.loads((tmp_path / "mjx-run/report/runtime.json").read_text())
    assert runtime["schema_version"] == 2
    assert runtime["outcome"] == "completed"
    assert [phase["name"] for phase in runtime["phases"]] == [
        "environment_setup",
        "initial_checkpoint",
        "playground_compile_and_train",
        "checkpoint_publish",
        "artifact_sync",
    ]


def test_train_mjx_writes_failed_runtime_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {"training.total_steps": 128, "training.n_envs": 4, "storage.mode": "local"},
    )
    monkeypatch.setattr(
        "sim2policy.train_mjx.validate_mjx_environment",
        lambda selected: {"environment": selected.environment, "impl": "jax"},
    )

    def fail(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(subprocess.CalledProcessError):
        train_mjx(config, "mjx-failed", tmp_path, runner=fail)
    runtime = json.loads((tmp_path / "mjx-failed/report/runtime.json").read_text())
    assert runtime["outcome"] == "failed"
    assert runtime["phases"][-1]["name"] == "playground_compile_and_train"


def test_train_mjx_extracts_zipped_resume_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "training.total_steps": 256,
            "training.n_envs": 4,
            "storage.mode": "local",
        },
    )
    monkeypatch.setattr(
        "sim2policy.train_mjx.validate_mjx_environment",
        lambda config: {"environment": config.environment, "impl": "jax"},
    )
    resume = train_mjx(config, "mjx-first", tmp_path, runner=_fake_checkpoint_runner("128"))

    seen_command: list[str] = []

    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        seen_command.extend(command)
        return _fake_checkpoint_runner("256")(command, **_)

    train_mjx(config, "mjx-resume", tmp_path, resume=resume, runner=runner)
    load_flag = next(part for part in seen_command if part.startswith("--load_checkpoint_path="))
    resume_path = Path(load_flag.removeprefix("--load_checkpoint_path="))
    assert resume_path.is_dir()
    assert (resume_path / "manifest.ocdbt").is_file()


def test_locomotion_success_reporting_for_mjx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "evaluation.episodes": 2,
            "storage.mode": "local",
        },
    )
    checkpoint = tmp_path / "checkpoint.zip"
    checkpoint.write_bytes(b"fake")

    def fake_evaluate_mjx(checkpoint: Path, config: object) -> tuple[list[dict[str, Any]], float]:
        return (
            [
                {"index": 0, "seed": 0, "reward": 1.0, "length": 50, "success": True},
                {"index": 1, "seed": 1, "reward": 2.0, "length": 50, "success": True},
            ],
            3.5,
        )

    monkeypatch.setattr("sim2policy.train_mjx.evaluate_mjx", fake_evaluate_mjx)
    metrics = evaluate(checkpoint, config, "mjx-report", tmp_path)
    assert metrics["success"] == {
        "met": True,
        "criterion": "velocity >= 0.5 and not fallen",
    }


def test_evaluate_mjx_restores_policy_and_records_locomotion_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del tmp_path
    config = load_config(
        ROOT / "configs/go1_mjx.yaml",
        {
            "evaluation.episodes": 2,
            "evaluation.seeds": [7, 9],
            "training.hyperparameters": {"impl": "jax", "episode_length": 3},
        },
    )

    class Random:
        @staticmethod
        def PRNGKey(seed: int) -> int:
            return seed

        @staticmethod
        def split(key: int) -> tuple[int, int]:
            return key + 1, key + 2

    class FakeJax:
        random = Random()

        class numpy:
            @staticmethod
            def asarray(value: Any, dtype: str) -> Any:
                class Array(list):
                    pass

                if isinstance(value, list):
                    result: Any = Array(value)
                else:
                    result = type("Scalar", (int,), {})(value)
                result.dtype = dtype
                return result

        @staticmethod
        def jit(function: Callable[..., Any]) -> Callable[..., Any]:
            return function

    class Data:
        qvel = [0.75]

    class State:
        def __init__(self) -> None:
            self.obs = [0.0]
            self.reward = 1.25
            self.done = False
            self.data = Data()
            self.info = {
                "command": type("Command", (list,), {"dtype": "float32"})([0.0] * 3),
                "steps_until_next_cmd": type(
                    "Counter", (int,), {"dtype": "int32"}
                )(1),
            }

        def replace(self, **updates: Any) -> State:
            state = State()
            state.__dict__.update(self.__dict__)
            state.__dict__.update(updates)
            return state

    class Environment:
        def reset(self, key: int) -> State:
            del key
            return State()

        def step(self, state: State, action: int) -> State:
            del action
            assert state.info["command"] == [1.0, 0.0, 0.0]
            return state

        def _get_obs(self, data: Data, info: dict[str, Any]) -> list[float]:
            del data
            return list(info["command"])

        def get_local_linvel(self, data: Data) -> list[float]:
            del data
            return [0.75, 0.0, 0.0]

    @contextmanager
    def session(checkpoint: Path, selected: object) -> Any:
        del checkpoint, selected
        yield FakeJax(), Environment(), lambda obs, key: (0, {})

    monkeypatch.setattr("sim2policy.train_mjx.mjx_policy_session", session)
    episodes, _ = evaluate_mjx(Path("policy.zip"), config)
    assert [episode["seed"] for episode in episodes] == [7, 9]
    assert all(episode["length"] == 3 for episode in episodes)
    assert all(episode["command_velocity"] == 1.0 for episode in episodes)
    assert all(episode["mean_velocity"] == 0.75 for episode in episodes)
    assert all(episode["success"] for episode in episodes)


def test_g1_command_cadence_contact_observation_and_pelvis_velocity() -> None:
    class FakeJax:
        class numpy:
            @staticmethod
            def asarray(value: Any, dtype: str | None = None) -> Any:
                del dtype
                return value

    class Data:
        sensordata = [1.0, 0.0]

    class State:
        def __init__(self) -> None:
            self.data = Data()
            self.info = {
                "command": type("Command", (list,), {"dtype": "float32"})([0.0] * 3),
                "step": 0,
            }
            self.obs: Any = None

        def replace(self, **updates: Any) -> State:
            state = State()
            state.__dict__.update(self.__dict__)
            state.__dict__.update(updates)
            return state

    class Model:
        sensor_adr = [0, 1]

    class Environment:
        _feet_floor_found_sensor = [0, 1]
        _mj_model = Model()

        def _get_obs(
            self, data: Data, info: dict[str, Any], contact: list[bool]
        ) -> dict[str, list[Any]]:
            del data
            assert contact == [True, False]
            return {"state": [*info["command"], *contact]}

        def get_local_linvel(self, data: Data, body: str) -> list[float]:
            del data
            assert body == "pelvis"
            return [0.6, 0.0, 0.0]

    environment = Environment()
    state = fixed_forward_command_state(
        State(), environment, FakeJax(), target_velocity=1.0, horizon=1000
    )
    assert state.info["command"] == [1.0, 0.0, 0.0]
    assert state.info["step"] == -1000
    assert state.obs == {"state": [1.0, 0.0, 0.0, True, False]}
    assert local_forward_velocity(environment, state) == 0.6


def test_mjx_backend_stays_optional_in_base_environment() -> None:
    if importlib.util.find_spec("jax") is not None:  # pragma: no cover - optional env
        pytest.skip("MJX optional dependencies are installed in this environment")
    with pytest.raises(RuntimeError, match="uv sync --extra mjx"):
        from sim2policy.train_mjx import require_mjx

        require_mjx()


def _fake_checkpoint_runner(*steps: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        logdir = next(
            part.removeprefix("--logdir=") for part in command if part.startswith("--logdir=")
        )
        for step in steps:
            checkpoint_dir = Path(logdir) / "experiment" / "checkpoints" / step
            checkpoint_dir.mkdir(parents=True)
            (checkpoint_dir / "manifest.ocdbt").write_text("fake", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    return runner


@pytest.fixture(autouse=True)
def fake_initial_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    def create(config: object, output_root: Path) -> Path:
        del config
        checkpoint = output_root / "000000000000"
        checkpoint.mkdir(parents=True)
        (checkpoint / "manifest.ocdbt").write_text("initial", encoding="utf-8")
        return checkpoint

    monkeypatch.setattr("sim2policy.train_mjx._create_initial_checkpoint_isolated", create)
    monkeypatch.setattr(
        "sim2policy.train_mjx.jax_device_info",
        lambda: ("gpu", [{"id": 0, "platform": "gpu", "kind": "Fake H100"}]),
    )
