from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sim2policy import train_sb3
from sim2policy.checkpoint import checkpoint_path, write_checkpoint_metadata
from sim2policy.config import load_config
from sim2policy.run import create_run_paths

ROOT = Path(__file__).parents[1]


class FakeBaseCallback:
    def __init__(self, verbose: int = 0) -> None:
        self.verbose = verbose
        self.model: FakeModel


class FakeCallbackList:
    def __init__(self, callbacks: list[Any]) -> None:
        self.callbacks = callbacks

    def _on_training_start(self) -> None:
        for callback in self.callbacks:
            callback._on_training_start()

    def _on_step(self) -> bool:
        return all(callback._on_step() for callback in self.callbacks)


class FakeEvalCallback(FakeBaseCallback):
    created: list[FakeEvalCallback] = []

    def __init__(
        self,
        eval_env: Any,
        *,
        best_model_save_path: str,
        log_path: str,
        eval_freq: int,
        n_eval_episodes: int,
        deterministic: bool,
        render: bool,
        warn: bool,
    ) -> None:
        super().__init__()
        self.eval_env = eval_env
        self.best_model_save_path = best_model_save_path
        self.log_path = log_path
        self.eval_freq = eval_freq
        self.n_eval_episodes = n_eval_episodes
        self.deterministic = deterministic
        self.render = render
        self.warn = warn
        FakeEvalCallback.created.append(self)

    def _on_training_start(self) -> None:
        return None

    def _on_step(self) -> bool:
        return True


class FakeEnv:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeModel:
    interrupt = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.num_timesteps = int(kwargs.pop("num_timesteps", 0))
        self.args = args
        self.kwargs = kwargs

    def save(self, prefix: Path) -> None:
        Path(str(prefix) + ".zip").write_bytes(f"model-{self.num_timesteps}".encode())

    def learn(
        self,
        *,
        total_timesteps: int,
        callback: Any,
        reset_num_timesteps: bool,
        tb_log_name: str,
    ) -> None:
        del reset_num_timesteps, tb_log_name

        def bind(item: Any) -> None:
            if hasattr(item, "callbacks"):
                for child in item.callbacks:
                    bind(child)
            item.model = self

        bind(callback)
        callback._on_training_start()
        if self.interrupt:
            self.num_timesteps += 64
            raise KeyboardInterrupt
        for _ in range(max(total_timesteps // 64, 1)):
            self.num_timesteps += 64
            callback._on_step()


class FakePPO(FakeModel):
    constructed: list[FakeModel] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.constructed.append(self)

    @staticmethod
    def load(checkpoint: Path, **kwargs: Any) -> FakePPO:
        metadata = json.loads(checkpoint.with_suffix(".zip.json").read_text())
        return FakePPO(num_timesteps=metadata["step"], **kwargs)


def install_fakes(monkeypatch: pytest.MonkeyPatch) -> list[FakeEnv]:
    envs: list[FakeEnv] = []

    def fake_make_vec_env(*_: Any, **__: Any) -> FakeEnv:
        env = FakeEnv()
        envs.append(env)
        return env

    FakeEvalCallback.created.clear()
    FakeModel.interrupt = False
    monkeypatch.setattr(
        train_sb3,
        "_imports",
        lambda: (FakePPO, FakeBaseCallback, FakeCallbackList, FakeEvalCallback, fake_make_vec_env),
    )
    return envs


def test_checkpoint_callback_cadence_and_eval_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch)
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    paths = create_run_paths("callback", tmp_path)
    synced: list[Path] = []
    callback = train_sb3.build_checkpoint_callback(
        config, paths, synced.append, eval_env=FakeEnv()
    )
    model = FakeModel(num_timesteps=0)
    for child in callback.callbacks:
        child.model = model
    callback._on_training_start()
    model.num_timesteps = 127
    assert callback._on_step()
    assert not synced
    model.num_timesteps = 128
    assert callback._on_step()
    assert synced == [paths.checkpoints / "step-000000000128.zip"]
    assert FakeEvalCallback.created[0].eval_freq == 128


def test_train_creates_initial_final_eval_and_closes_envs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    envs = install_fakes(monkeypatch)
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    final = train_sb3.train(config, "fake-train", tmp_path)
    run_root = tmp_path / "fake-train"
    assert (run_root / "checkpoints" / "initial-000000000000.zip").is_file()
    assert final == run_root / "checkpoints" / "final-000000000256.zip"
    assert (run_root / "report" / "eval").is_dir()
    assert all(env.closed for env in envs)


def test_resume_preserves_timestep_numbering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch)
    config = load_config(ROOT / "configs/smoke_sb3.yaml", {"training.total_steps": 256})
    source_root = tmp_path / "source"
    resume = checkpoint_path(source_root / "checkpoints", "step", 128)
    resume.parent.mkdir(parents=True)
    resume.write_bytes(b"resume")
    write_checkpoint_metadata(resume, config, 128)
    final = train_sb3.train(config, "resume-run", tmp_path, resume=resume)
    assert final.name == "final-000000000256.zip"


def test_interruption_saves_snapshot_and_syncs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch)
    FakeModel.interrupt = True
    config = load_config(ROOT / "configs/smoke_sb3.yaml")
    synced: list[Path] = []
    with pytest.raises(KeyboardInterrupt):
        train_sb3.train(config, "interrupt-run", tmp_path, sync_hook=synced.append)
    interrupted = tmp_path / "interrupt-run" / "checkpoints" / "interrupted-000000000064.zip"
    assert interrupted.is_file()
    assert synced == [interrupted]
