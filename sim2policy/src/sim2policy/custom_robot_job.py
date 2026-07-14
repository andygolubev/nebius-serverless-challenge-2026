"""Fixed preparation and training modes for inert custom-robot runtime inputs."""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import json
import math
import platform
import signal
import sys
import tempfile
import time
import zipfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, cast

import imageio.v2 as imageio
import numpy as np

from sim2policy.custom_robot_contract import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    SCENE_VERSION,
    SCHEMA_VERSION,
    TRAINING_PROFILE,
    TRAINING_PROFILE_VERSION,
    PreparationProfile,
    TrainingProfile,
    canonical_json,
    sha256_bytes,
    validate_safe_id,
)
from sim2policy.custom_robot_env import (
    CustomRobotCompatibilityError,
    CustomRobotEnv,
    make_vectorized_env,
)
from sim2policy.custom_robot_io import (
    CustomInputDocuments,
    CustomInputError,
    load_inputs_from_directory,
    load_inputs_from_s3,
    put_s3_bytes,
)

PREPARATION_REPORT = "report/preparation.json"
PREPARATION_PROBE = "report/render-probe.png"
REQUIRED_BUNDLE_MEMBERS = (
    "README.md",
    "checkpoint/policy.zip",
    "robot/robot.xml",
    "setup/normalized-setup.json",
    "config/resolved-config.json",
    "runtime/versions.json",
    "evaluation/metrics.json",
)


class PhaseTimeout(TimeoutError):
    pass


@dataclass
class PhaseRecord:
    name: str
    status: str
    duration_seconds: float
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 6),
            "metrics": self.metrics,
        }


class Publisher:
    def __init__(self, identity: str, kind: str, local_root: Path | None) -> None:
        validate_safe_id(identity)
        self.identity = identity
        self.kind = kind
        self.local_root = local_root.resolve() if local_root else None
        self.prefix = (
            f"sim2policy/preparations/{identity}"
            if kind == "preparation"
            else f"sim2policy/{identity}"
        )

    def put(self, relative: str, data: bytes, content_type: str) -> None:
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or not relative:
            raise ValueError("output path is outside the fixed run layout")
        if self.local_root is not None:
            destination = self.local_root / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".partial")
            temporary.write_bytes(data)
            temporary.replace(destination)
            return
        put_s3_bytes(f"{self.prefix}/{relative}", data, content_type=content_type)

    def put_json(self, relative: str, value: dict[str, Any]) -> bytes:
        data = canonical_json(value)
        self.put(relative, data, "application/json")
        return data


def _timeout_handler(_signum: int, _frame: Any) -> None:
    raise PhaseTimeout("phase-timeout")


@contextlib.contextmanager
def bounded_phase(seconds: int) -> Iterator[None]:
    if seconds <= 0 or not hasattr(signal, "setitimer"):
        yield
        return
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    previous = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        if previous[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous[0], previous[1])


def _versions() -> dict[str, str]:
    values = {
        "adapter": ADAPTER_VERSION,
        "reward": REWARD_VERSION,
        "scene": SCENE_VERSION,
        "preparation_profile": PREPARATION_PROFILE_VERSION,
        "training_profile": TRAINING_PROFILE_VERSION,
        "python": platform.python_version(),
    }
    for package in ("mujoco", "gymnasium", "stable-baselines3", "numpy"):
        try:
            values[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            values[package] = "unavailable"
    return values


def _safe_failure(exc: BaseException) -> str:
    if isinstance(exc, CustomRobotCompatibilityError):
        return exc.reason
    if isinstance(exc, CustomInputError):
        return "input-contract-failed"
    if isinstance(exc, PhaseTimeout):
        return "phase-timeout"
    if isinstance(exc, MemoryError):
        return "resource-limit-exceeded"
    return "runtime-gate-failed"


def _report_hash(report: dict[str, Any]) -> str:
    payload = dict(report)
    payload.pop("report_sha256", None)
    return sha256_bytes(canonical_json(payload))


def _record_phase(
    phases: list[PhaseRecord],
    name: str,
    timeout: int,
    operation: Any,
) -> Any:
    started = time.monotonic()
    try:
        with bounded_phase(timeout):
            result = operation()
    except BaseException:
        phases.append(PhaseRecord(name, "failed", time.monotonic() - started, {}))
        raise
    metrics = result if isinstance(result, dict) else {}
    phases.append(PhaseRecord(name, "passed", time.monotonic() - started, metrics))
    return result


def _rollout_probe(documents: CustomInputDocuments, profile: PreparationProfile) -> dict[str, Any]:
    aggregate = {
        "steps": 0,
        "resets": 0,
        "terminations": 0,
        "contacts_max": 0,
        "abs_state_max": 0.0,
    }
    for seed in profile.rollout_seeds:
        env = CustomRobotEnv(documents.robot_xml, documents.setup)
        try:
            for policy in ("zero", "random"):
                observation, _ = env.reset(seed=seed)
                action_rng = np.random.default_rng(seed + (1000 if policy == "random" else 0))
                aggregate["resets"] += 1
                for _ in range(profile.rollout_steps):
                    action_shape = env.action_space.shape
                    assert action_shape is not None
                    action = (
                        np.zeros(action_shape, dtype=np.float32)
                        if policy == "zero"
                        else action_rng.uniform(-1.0, 1.0, size=action_shape).astype(np.float32)
                    )
                    observation, reward, terminated, truncated, info = env.step(action)
                    if not np.isfinite(observation).all() or not math.isfinite(reward):
                        raise CustomRobotCompatibilityError("rollout-non-finite")
                    metrics = info["task_metrics"]
                    if metrics["non_finite"] or metrics["runaway"]:
                        raise CustomRobotCompatibilityError("rollout-dynamics-invalid")
                    aggregate["steps"] += 1
                    aggregate["contacts_max"] = max(
                        int(aggregate["contacts_max"]), int(env.data.ncon)
                    )
                    aggregate["abs_state_max"] = max(
                        float(aggregate["abs_state_max"]),
                        float(np.max(np.abs(env.data.qpos))),
                        float(np.max(np.abs(env.data.qvel))),
                    )
                    if terminated or truncated:
                        aggregate["terminations"] += 1
                        env.reset(seed=seed + int(aggregate["terminations"]))
        finally:
            env.close()
    return aggregate


def _render_probe(documents: CustomInputDocuments, destination: Path) -> dict[str, Any]:
    env = CustomRobotEnv(documents.robot_xml, documents.setup, render_mode="rgb_array")
    try:
        env.reset(seed=7)
        frame = env.render()
        if frame is None or frame.shape != (480, 640, 3) or frame.dtype != np.uint8:
            raise CustomRobotCompatibilityError("render-frame-invalid")
        imageio.imwrite(str(destination), frame, format="png")  # type: ignore[call-overload]
    finally:
        env.close()
    return {"width": 640, "height": 480, "size_bytes": destination.stat().st_size}


def _checker_probe(documents: CustomInputDocuments) -> dict[str, Any]:
    from stable_baselines3.common.env_checker import check_env

    env = CustomRobotEnv(documents.robot_xml, documents.setup)
    try:
        check_env(env, warn=False, skip_render_check=True)
    finally:
        env.close()
    return {"gymnasium": "passed", "sb3": "passed"}


def _ppo_probe(documents: CustomInputDocuments, output: Path, steps: int) -> dict[str, Any]:
    from stable_baselines3 import PPO

    env = CustomRobotEnv(documents.robot_xml, documents.setup)
    reloaded = None
    try:
        model = PPO(
            "MlpPolicy",
            env,
            seed=101,
            learning_rate=3e-4,
            n_steps=min(256, steps),
            batch_size=64,
            n_epochs=2,
            verbose=0,
            device="cpu",
        )
        model.learn(total_timesteps=steps)
        model.save(output)
        archive = output.with_suffix(".zip")
        reloaded = PPO.load(archive, env=env, device="cpu")
        observation, _ = env.reset(seed=211)
        rewards: list[float] = []
        for _ in range(64):
            action, _ = reloaded.predict(observation, deterministic=True)
            observation, reward, terminated, truncated, _ = env.step(action)
            if not math.isfinite(reward):
                raise CustomRobotCompatibilityError("ppo-inference-non-finite")
            rewards.append(reward)
            if terminated or truncated:
                observation, _ = env.reset(seed=223)
        return {
            "learning_steps": steps,
            "inference_steps": len(rewards),
            "mean_inference_reward": float(np.mean(rewards)),
            "checkpoint_size_bytes": archive.stat().st_size,
        }
    finally:
        if reloaded is not None:
            reloaded.set_env(env)
        env.close()


def run_preparation(
    documents: CustomInputDocuments,
    publisher: Publisher,
    *,
    profile: PreparationProfile = PREPARATION_PROFILE,
) -> dict[str, Any]:
    phases: list[PhaseRecord] = []
    compiled: dict[str, Any] = {}
    schemas: dict[str, Any] = {}
    failure_phase: str | None = None
    failure_reason: str | None = None
    with tempfile.TemporaryDirectory(prefix="sim2policy-custom-prepare-") as raw_temporary:
        temporary = Path(raw_temporary)
        render_path = temporary / "render-probe.png"
        checkpoint_path = temporary / "ppo-smoke"
        try:

            def compile_probe() -> dict[str, Any]:
                nonlocal compiled, schemas
                env = CustomRobotEnv(documents.robot_xml, documents.setup)
                try:
                    resolved = env.resolved_contract()
                    compiled = resolved["compiled"]
                    schemas = resolved["schemas"]
                    observation, _ = env.reset(seed=profile.rollout_seeds[0])
                    if not env.observation_space.contains(observation):
                        raise CustomRobotCompatibilityError("observation-space-invalid")
                    return compiled
                finally:
                    env.close()

            _record_phase(phases, "compile", profile.compile_timeout_seconds, compile_probe)
            _record_phase(
                phases,
                "rollouts",
                profile.rollout_timeout_seconds,
                lambda: _rollout_probe(documents, profile),
            )
            render_metrics = _record_phase(
                phases,
                "render",
                profile.render_timeout_seconds,
                lambda: _render_probe(documents, render_path),
            )
            if render_metrics["size_bytes"] > profile.max_render_bytes:
                raise CustomRobotCompatibilityError("render-output-too-large")
            _record_phase(
                phases,
                "environment-checker",
                profile.checker_timeout_seconds,
                lambda: _checker_probe(documents),
            )
            _record_phase(
                phases,
                "ppo-smoke",
                profile.learning_timeout_seconds,
                lambda: _ppo_probe(documents, checkpoint_path, profile.smoke_learning_steps),
            )
            status = "accepted"
        except BaseException as exc:
            status = "failed"
            failure_phase = phases[-1].name if phases else "inputs"
            failure_reason = _safe_failure(exc)

        report = {
            "schema_version": SCHEMA_VERSION,
            "preparation_id": str(documents.manifest["preparation_id"]),
            "fingerprint": documents.fingerprint,
            "status": status,
            "failure_phase": failure_phase,
            "failure_reason": failure_reason,
            "phases": [phase.to_dict() for phase in phases],
            "compiled": compiled,
            "schemas": schemas,
            "versions": _versions(),
            "report_sha256": "",
        }
        report["report_sha256"] = _report_hash(report)
        encoded = canonical_json(report)
        if len(encoded) > profile.max_report_bytes:
            raise RuntimeError("bounded preparation report unexpectedly exceeded its contract")
        if render_path.is_file() and render_path.stat().st_size <= profile.max_render_bytes:
            publisher.put(PREPARATION_PROBE, render_path.read_bytes(), "image/png")
        publisher.put(PREPARATION_REPORT, encoded, "application/json")
        return report


def _evaluate_policy(
    model: Any,
    documents: CustomInputDocuments,
    profile: TrainingProfile,
) -> dict[str, Any]:
    episodes: list[dict[str, Any]] = []
    for index in range(profile.evaluation_episodes):
        seed = profile.evaluation_seeds[index % len(profile.evaluation_seeds)] + index
        env = CustomRobotEnv(documents.robot_xml, documents.setup)
        try:
            observation, _ = env.reset(seed=seed)
            total_reward = 0.0
            final_metrics: dict[str, Any] = {}
            length = 0
            for step in range(1, int(env.contract["episode_steps"]) + 1):
                length = step
                action, _ = model.predict(observation, deterministic=True)
                observation, reward, terminated, truncated, info = env.step(action)
                total_reward += reward
                final_metrics = dict(info["task_metrics"])
                if terminated or truncated:
                    break
            episodes.append(
                {
                    "index": index,
                    "seed": seed,
                    "reward": total_reward,
                    "length": length,
                    "success": bool(final_metrics.get("success")),
                    "fallen": bool(final_metrics.get("fallen")),
                    "task_metrics": final_metrics,
                }
            )
        finally:
            env.close()
    rewards = [float(item["reward"]) for item in episodes]
    return {
        "episodes": episodes,
        "aggregate": {
            "episodes": len(episodes),
            "mean_reward": float(np.mean(rewards)),
            "std_reward": float(np.std(rewards)),
            "success_rate": float(np.mean([bool(item["success"]) for item in episodes])),
            "fall_rate": float(np.mean([bool(item["fallen"]) for item in episodes])),
            "task_threshold_achieved": bool(all(item["success"] for item in episodes)),
        },
    }


def _render_video(model: Any, documents: CustomInputDocuments, output: Path) -> dict[str, Any]:
    env = CustomRobotEnv(documents.robot_xml, documents.setup, render_mode="rgb_array")
    writer = imageio.get_writer(output, fps=50, codec="libx264", quality=7)
    frames = 0
    try:
        observation, _ = env.reset(seed=307)
        for step in range(500):
            if step % 2 == 0:
                frame = env.render()
                assert frame is not None
                writer.append_data(frame)
                frames += 1
            action, _ = model.predict(observation, deterministic=True)
            observation, _, terminated, truncated, _ = env.step(action)
            if terminated or truncated:
                break
    finally:
        writer.close()
        env.close()
    if frames < 2 or not output.is_file() or output.stat().st_size == 0:
        raise CustomRobotCompatibilityError("final-video-invalid")
    return {"frames": frames, "size_bytes": output.stat().st_size}


def _reward_curve(rewards: list[float], output: Path) -> None:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(7, 3.2))
    axis.plot(np.arange(len(rewards)), rewards, color="#4f46e5", linewidth=1.4)
    axis.set(xlabel="Episode", ylabel="Reward", title="Custom PPO training reward")
    axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output, dpi=140)
    plt.close(figure)


def _bundle_member(path: str, data: bytes, content_type: str) -> dict[str, Any]:
    return {
        "path": path,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
        "content_type": content_type,
    }


def build_policy_bundle(
    output: Path,
    *,
    fingerprint: str,
    robot_xml: bytes,
    normalized_setup: bytes,
    checkpoint: bytes,
    resolved_config: bytes,
    versions: bytes,
    evaluation: bytes,
) -> dict[str, Any]:
    readme = (
        b"# Sim2Policy custom robot policy\n\n"
        b"SIMULATOR ONLY. This bundle is not directly deployable to a physical robot. "
        b"It was trained for the included MuJoCo model, task, scene, adapter, and runtime.\n"
    )
    contents = {
        "README.md": (readme, "text/markdown"),
        "checkpoint/policy.zip": (checkpoint, "application/zip"),
        "robot/robot.xml": (robot_xml, "application/xml"),
        "setup/normalized-setup.json": (normalized_setup, "application/json"),
        "config/resolved-config.json": (resolved_config, "application/json"),
        "runtime/versions.json": (versions, "application/json"),
        "evaluation/metrics.json": (evaluation, "application/json"),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "custom-robot-policy-bundle",
        "fingerprint": fingerprint,
        "backend": "sb3",
        "profile": "custom-ppo-quick",
        "simulator_only": True,
        "members": [
            _bundle_member(path, data, content_type)
            for path, (data, content_type) in contents.items()
        ],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, (data, _) in contents.items():
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
        info = zipfile.ZipInfo("manifest.json", date_time=(2026, 1, 1, 0, 0, 0))
        info.external_attr = 0o600 << 16
        archive.writestr(info, canonical_json(manifest), compress_type=zipfile.ZIP_DEFLATED)
    inspect_policy_bundle(output, expected_fingerprint=fingerprint)
    return cast(dict[str, Any], manifest)


def inspect_policy_bundle(path: Path, *, expected_fingerprint: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > TRAINING_PROFILE.max_artifact_bytes:
        raise ValueError("policy bundle size is invalid")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or name.endswith("/"):
                raise ValueError("policy bundle contains an unsafe member")
            if archive.getinfo(name).file_size > TRAINING_PROFILE.max_artifact_bytes:
                raise ValueError("policy bundle member size is invalid")
        if set(names) != {*REQUIRED_BUNDLE_MEMBERS, "manifest.json"}:
            raise ValueError("policy bundle layout is invalid")
        manifest = json.loads(archive.read("manifest.json"))
        if (
            manifest.get("fingerprint") != expected_fingerprint
            or manifest.get("simulator_only") is not True
        ):
            raise ValueError("policy bundle provenance is invalid")
        descriptors = {item["path"]: item for item in manifest.get("members", [])}
        if set(descriptors) != set(REQUIRED_BUNDLE_MEMBERS):
            raise ValueError("policy bundle manifest is incomplete")
        for name in REQUIRED_BUNDLE_MEMBERS:
            data = archive.read(name)
            descriptor = descriptors[name]
            if descriptor.get("size_bytes") != len(data) or descriptor.get(
                "sha256"
            ) != sha256_bytes(data):
                raise ValueError("policy bundle member digest is invalid")
    return cast(dict[str, Any], manifest)


def smoke_load_policy_bundle(path: Path, *, expected_fingerprint: str) -> None:
    """Load the archived policy against its exact bundled model and take one action."""
    from stable_baselines3 import PPO

    inspect_policy_bundle(path, expected_fingerprint=expected_fingerprint)
    with (
        zipfile.ZipFile(path) as archive,
        tempfile.TemporaryDirectory(prefix="sim2policy-bundle-smoke-") as raw_temporary,
    ):
        root = Path(raw_temporary)
        checkpoint = root / "policy.zip"
        checkpoint.write_bytes(archive.read("checkpoint/policy.zip"))
        robot_xml = archive.read("robot/robot.xml").decode("utf-8")
        setup = json.loads(archive.read("setup/normalized-setup.json"))
        env = CustomRobotEnv(robot_xml, setup)
        try:
            model = PPO.load(checkpoint, env=env, device="cpu")
            observation, _ = env.reset(seed=503)
            action, _ = model.predict(observation, deterministic=True)
            next_observation, reward, _, _, _ = env.step(action)
            if not np.isfinite(next_observation).all() or not math.isfinite(reward):
                raise ValueError("policy bundle inference is non-finite")
        finally:
            env.close()


def run_training(
    documents: CustomInputDocuments,
    publisher: Publisher,
    *,
    profile: TrainingProfile = TRAINING_PROFILE,
) -> dict[str, Any]:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback

    started_at = time.monotonic()
    validate_safe_id(publisher.identity, "run identity")
    with tempfile.TemporaryDirectory(prefix="sim2policy-custom-train-") as raw_temporary:
        root = Path(raw_temporary)
        checkpoint_dir = root / "checkpoints"
        checkpoint_dir.mkdir()
        vector = make_vectorized_env(
            documents.robot_xml,
            documents.setup,
            seed=401,
            n_envs=profile.n_envs,
        )
        episode_rewards: list[float] = []
        progress_evaluations: list[dict[str, Any]] = []

        class RewardCallback(BaseCallback):
            def _on_step(self) -> bool:
                for info in self.locals.get("infos", []):
                    episode = info.get("episode")
                    if isinstance(episode, dict) and "r" in episode:
                        episode_rewards.append(float(episode["r"]))
                return True

        class DurableProgressCallback(BaseCallback):
            """Publish only complete checkpoints and bounded evaluation summaries."""

            def __init__(self) -> None:
                super().__init__()
                self.next_checkpoint = profile.checkpoint_every_steps
                self.next_evaluation = profile.evaluation_every_steps

            def _on_step(self) -> bool:
                timesteps = int(self.num_timesteps)
                if timesteps >= self.next_checkpoint:
                    checkpoint = checkpoint_dir / f"step-{timesteps:09d}"
                    self.model.save(checkpoint)
                    archive = checkpoint.with_suffix(".zip")
                    publisher.put(
                        f"checkpoints/step-{timesteps:09d}.zip",
                        archive.read_bytes(),
                        "application/zip",
                    )
                    while self.next_checkpoint <= timesteps:
                        self.next_checkpoint += profile.checkpoint_every_steps
                if timesteps >= self.next_evaluation:
                    interim_profile = replace(
                        profile,
                        evaluation_episodes=profile.progress_evaluation_episodes,
                        evaluation_seeds=profile.progress_evaluation_seeds,
                    )
                    evaluation = _evaluate_policy(self.model, documents, interim_profile)
                    progress_evaluations.append(
                        {
                            "timesteps": timesteps,
                            "aggregate": evaluation["aggregate"],
                        }
                    )
                    publisher.put_json(
                        "metadata/progress.json",
                        {
                            "run_id": publisher.identity,
                            "status": "training",
                            "progress": {
                                "phase": "training",
                                "timesteps": timesteps,
                                "total_timesteps": profile.total_timesteps,
                                "evaluations": progress_evaluations,
                            },
                        },
                    )
                    while self.next_evaluation <= timesteps:
                        self.next_evaluation += profile.evaluation_every_steps
                return True

        try:
            publisher.put_json(
                "metadata/status.json",
                {
                    "run_id": publisher.identity,
                    "status": "training",
                    "progress": {
                        "phase": "training",
                        "timesteps": 0,
                        "total_timesteps": profile.total_timesteps,
                    },
                },
            )
            model = PPO(
                "MlpPolicy",
                vector,
                seed=401,
                learning_rate=profile.ppo_learning_rate,
                n_steps=profile.ppo_n_steps,
                batch_size=profile.ppo_batch_size,
                n_epochs=profile.ppo_n_epochs,
                gamma=profile.ppo_gamma,
                gae_lambda=profile.ppo_gae_lambda,
                clip_range=profile.ppo_clip_range,
                verbose=0,
                device="cpu",
            )
            model.learn(
                total_timesteps=profile.total_timesteps,
                callback=[
                    DurableProgressCallback(),
                    RewardCallback(),
                ],
            )
            final = checkpoint_dir / "final"
            model.save(final)
            final_zip = final.with_suffix(".zip")
            reloaded = PPO.load(final_zip, env=vector, device="cpu")
            evaluation = _evaluate_policy(reloaded, documents, profile)
            video_path = root / "final.mp4"
            video = _render_video(reloaded, documents, video_path)
        finally:
            vector.close()

        resolved_env = CustomRobotEnv(documents.robot_xml, documents.setup)
        try:
            adapter = resolved_env.resolved_contract()
        finally:
            resolved_env.close()
        resolved: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "job_kind": "custom-robot",
            "backend": "sb3",
            "profile": "custom-ppo-quick",
            "robot": {
                "digest": documents.manifest["robot"]["source_digest"],
            },
            "setup": documents.setup,
            "preparation": {
                "fingerprint": documents.fingerprint,
            },
            "runtime": {"image_digest": documents.manifest["runtime"]["image_digest"]},
            "adapter": adapter,
            "training": asdict(profile),
        }
        resolved["training"]["evaluation_seeds"] = list(profile.evaluation_seeds)
        resolved["training"]["progress_evaluation_seeds"] = list(
            profile.progress_evaluation_seeds
        )
        runtime_seconds = time.monotonic() - started_at
        metrics = {
            **evaluation,
            "runtime_seconds": runtime_seconds,
            "benchmark": {
                "hourly_rate": profile.hourly_rate,
                "currency": profile.currency,
                "rate_date": profile.rate_date,
                "estimated_cost": runtime_seconds / 3600 * profile.hourly_rate,
            },
            "training": {
                "timesteps": profile.total_timesteps,
                "episode_rewards": episode_rewards[-5000:],
                "progress_evaluations": progress_evaluations,
            },
            "video": video,
            "simulator_only": True,
        }
        versions = _versions()
        resolved_bytes = canonical_json(resolved)
        metrics_bytes = canonical_json(metrics)
        versions_bytes = canonical_json(versions)
        curve_path = root / "reward-curve.png"
        _reward_curve(episode_rewards or [0.0], curve_path)
        report = (
            "# Custom robot training result\n\n"
            f"Task threshold achieved: **{evaluation['aggregate']['task_threshold_achieved']}**\n\n"
            f"Mean reward: {evaluation['aggregate']['mean_reward']:.3f}\n\n"
            "The policy bundle is simulator-only and is not directly deployable "
            "to physical hardware.\n"
        ).encode()
        setup_bytes = canonical_json(documents.setup)
        bundle_path = root / "policy-bundle.zip"
        bundle_manifest = build_policy_bundle(
            bundle_path,
            fingerprint=documents.fingerprint,
            robot_xml=documents.robot_xml.encode(),
            normalized_setup=setup_bytes,
            checkpoint=final_zip.read_bytes(),
            resolved_config=resolved_bytes,
            versions=versions_bytes,
            evaluation=metrics_bytes,
        )
        smoke_load_policy_bundle(bundle_path, expected_fingerprint=documents.fingerprint)
        artifacts: dict[str, tuple[str, bytes, str]] = {
            "final_policy": ("checkpoints/final.zip", final_zip.read_bytes(), "application/zip"),
            "metrics_json": ("report/metrics.json", metrics_bytes, "application/json"),
            "report_md": ("report/report.md", report, "text/markdown"),
            "reward_curve": ("report/reward-curve.png", curve_path.read_bytes(), "image/png"),
            "video_final": ("videos/final.mp4", video_path.read_bytes(), "video/mp4"),
            "resolved_config": ("report/resolved-config.json", resolved_bytes, "application/json"),
            "runtime_versions": (
                "report/runtime-versions.json",
                versions_bytes,
                "application/json",
            ),
            "policy_bundle": (
                "bundle/policy-bundle.zip",
                bundle_path.read_bytes(),
                "application/zip",
            ),
            "bundle_manifest": (
                "bundle/manifest.json",
                canonical_json(bundle_manifest),
                "application/json",
            ),
            "robot_xml": ("inputs/robot.xml", documents.robot_xml.encode(), "application/xml"),
            "normalized_setup": ("inputs/normalized-setup.json", setup_bytes, "application/json"),
        }
        manifest: dict[str, Any] = {
            "artifacts": {name: values[0] for name, values in artifacts.items()}
        }
        manifest["checksums"] = {
            name: {"sha256": sha256_bytes(values[1]), "size_bytes": len(values[1])}
            for name, values in artifacts.items()
        }
        for _, (relative, data, content_type) in artifacts.items():
            if len(data) > profile.max_artifact_bytes:
                raise RuntimeError("custom training artifact exceeds fixed bound")
            publisher.put(relative, data, content_type)
        publisher.put_json(
            "metadata/status.json",
            {
                "run_id": publisher.identity,
                "status": "completed",
                "progress": {"phase": "completed", "timesteps": profile.total_timesteps},
            },
        )
        publisher.put_json("report/artifacts.json", manifest)
        return metrics


def _load(identity: str, mode: str, input_root: Path | None) -> CustomInputDocuments:
    if input_root is not None:
        return load_inputs_from_directory(input_root)
    return load_inputs_from_s3(
        identity,
        kind="preparation" if mode == "prepare" else "run",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed custom robot preparation or training")
    parser.add_argument("mode", choices=("prepare", "train"))
    parser.add_argument("--identity", required=True)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    try:
        validate_safe_id(args.identity)
        documents = _load(args.identity, args.mode, args.input_root)
        publisher = Publisher(
            args.identity,
            "preparation" if args.mode == "prepare" else "run",
            args.output_root,
        )
        if args.mode == "prepare":
            report = run_preparation(documents, publisher)
            return 0 if report["status"] == "accepted" else 2
        run_training(documents, publisher)
        return 0
    except Exception as exc:
        print(
            f"custom robot {args.mode} failed: {_safe_failure(exc)}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
