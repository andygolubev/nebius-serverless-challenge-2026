from __future__ import annotations

import argparse
import contextlib
import functools
import importlib
import inspect
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from sim2policy.checkpoint import (
    CheckpointError,
    checkpoint_path,
    latest_checkpoint,
    load_checkpoint_metadata,
    validate_checkpoint,
    write_checkpoint_metadata,
)
from sim2policy.config import RunConfig, load_config, parse_override
from sim2policy.g1_forward_env import (
    G1_FORWARD_FLAT_ENVIRONMENT,
    G1_FORWARD_ROUGH_ENVIRONMENT,
    is_g1_forward_environment,
    register_g1_forward_environments,
    upstream_environment,
)
from sim2policy.run import RunPaths, create_run_paths, write_metadata
from sim2policy.runstate import STATUS_FAILED, STATUS_TRAINING, RunStateStore
from sim2policy.storage import ArtifactStore
from sim2policy.telemetry import GpuSampler, runtime_record, utc_now_iso, write_runtime_record

_MJX_MODULES = ("jax", "mujoco", "mujoco_playground", "brax")
_BRAX_OPTIONAL_INITIALIZERS = (
    "policy_network_kernel_init_fn",
    "value_network_kernel_init_fn",
    "q_network_kernel_init_fn",
    "mean_kernel_init_fn",
)
_NETWORK_FACTORY_HYPERPARAMETERS = {
    "policy_hidden_layer_sizes",
    "value_hidden_layer_sizes",
    "policy_obs_key",
    "value_obs_key",
}
_PLAYGROUND_FLAG_MAP = {
    "num_eval_envs",
    "num_evals",
    "batch_size",
    "num_minibatches",
    "num_updates_per_batch",
    "unroll_length",
    "episode_length",
    "learning_rate",
    "entropy_cost",
    "discounting",
    "reward_scaling",
    "action_repeat",
    "clipping_epsilon",
    "max_grad_norm",
    "training_metrics_steps",
    "policy_obs_key",
    "value_obs_key",
    "policy_hidden_layer_sizes",
    "value_hidden_layer_sizes",
}
REVIEWED_RESUME_TRANSITIONS = frozenset(
    {
        ("G1JoystickFlatTerrain", "G1JoystickRoughTerrain"),
        (G1_FORWARD_FLAT_ENVIRONMENT, G1_FORWARD_ROUGH_ENVIRONMENT),
        # Retained rejected-campaign checkpoints are allowed only as the
        # explicitly named input to the bounded diagnostic pilot.
        ("G1JoystickFlatTerrain", G1_FORWARD_ROUGH_ENVIRONMENT),
    }
)

G1_TERMINATION_ORDER = (
    "nan_state",
    "torso_inversion",
    "foot_foot_contact",
    "foot_shin_contact",
    "unknown_environment_done",
)


def _environment_overrides(config: RunConfig) -> dict[str, Any]:
    overrides = {
        "impl": str(config.training.hyperparameters.get("impl", "jax"))
    }
    playground_overrides = config.training.hyperparameters.get(
        "playground_config_overrides", {}
    )
    overrides.update(playground_overrides)
    return overrides


def _json_flag(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def require_mjx() -> None:
    missing: list[str] = []
    for module in _MJX_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        raise RuntimeError(
            "MJX dependencies are unavailable: "
            + ", ".join(missing)
            + ". Install with `uv sync --extra mjx` or use the MJX container target."
        )


def validate_mjx_environment(config: RunConfig) -> dict[str, Any]:
    require_mjx()
    if is_g1_forward_environment(config.environment):
        register_g1_forward_environments()
    registry = importlib.import_module("mujoco_playground").registry
    env_overrides = _environment_overrides(config)
    try:
        env = registry.load(config.environment, config_overrides=env_overrides)
    except Exception as exc:
        raise RuntimeError(
            f"MJX environment `{config.environment}` failed to load with overrides "
            f"{env_overrides}. Use an explicit supported Playground environment and `impl: jax`."
        ) from exc
    return {
        "environment": config.environment,
        "impl": env_overrides["impl"],
        "observation_size": getattr(env, "observation_size", None),
        "action_size": getattr(env, "action_size", None),
    }


#: Set to "1" to permit MJX training on CPU. Intended only for CPU-only test hosts;
#: never for a GPU-priced job.
ALLOW_CPU_ENVIRONMENT_VARIABLE = "SIM2POLICY_ALLOW_CPU_MJX"


def require_accelerator(backend: str, devices: list[dict[str, Any]]) -> None:
    """Refuse to train MJX on CPU unless a CPU host was explicitly declared.

    JAX silently falls back to CPU when it cannot load the CUDA libraries, and MJX
    training still "works" — just orders of magnitude slower. On an H100 job that
    is invisible in the logs and shows up only as a GPU bill for CPU work, so the
    fallback is turned into an immediate, loud failure.
    """
    if backend.lower() == "gpu" or any(
        str(device.get("platform", "")).lower() == "gpu" for device in devices
    ):
        return
    if os.environ.get(ALLOW_CPU_ENVIRONMENT_VARIABLE) == "1":
        return
    raise RuntimeError(
        "MJX training found no GPU device (JAX backend "
        f"{backend!r}); refusing to run accelerator-priced training on CPU. "
        f"Set {ALLOW_CPU_ENVIRONMENT_VARIABLE}=1 only on a CPU-only host."
    )


def jax_device_info() -> tuple[str, list[dict[str, Any]]]:
    jax = importlib.import_module("jax")
    devices = [
        {
            "id": getattr(device, "id", None),
            "platform": getattr(device, "platform", None),
            "kind": getattr(device, "device_kind", type(device).__name__),
        }
        for device in jax.devices()
    ]
    return str(jax.default_backend()), devices


def build_playground_command(
    config: RunConfig,
    paths: RunPaths,
    *,
    resume: Path | None = None,
) -> list[str]:
    environment_overrides = _environment_overrides(config)
    hyperparameters = dict(config.training.hyperparameters)
    impl = str(hyperparameters.pop("impl", "jax"))
    hyperparameters.pop("playground_config_overrides", None)
    hyperparameters["num_evals"] = max(
        2, math.ceil(config.training.total_steps / config.checkpoint.every_steps) + 1
    )
    executable = (
        [sys.executable, "-m", "sim2policy.playground_train"]
        if is_g1_forward_environment(config.environment)
        else ["train-jax-ppo"]
    )
    command = [
        *executable,
        f"--env_name={config.environment}",
        f"--impl={impl}",
        f"--seed={config.seed}",
        f"--num_timesteps={config.training.total_steps}",
        f"--num_envs={config.training.n_envs}",
        f"--logdir={paths.root / 'mjx_logs'}",
        f"--suffix={paths.root.name}",
        "--nouse_wandb",
        "--use_tb",
        "--num_videos=0",
        "--playground_config_overrides",
        _json_flag(environment_overrides),
    ]
    if resume is not None:
        command.append(f"--load_checkpoint_path={resume}")
    unknown = sorted(set(hyperparameters) - _PLAYGROUND_FLAG_MAP - {"network_factory"})
    if unknown:
        raise RuntimeError(f"unsupported MJX hyperparameter(s): {', '.join(unknown)}")
    for key, value in sorted(hyperparameters.items()):
        if key in {"policy_hidden_layer_sizes", "value_hidden_layer_sizes"}:
            command.append(f"--{key}={','.join(str(item) for item in value)}")
        else:
            command.append(f"--{key}={value}")
    return command


def _playground_checkpoints(raw_log_root: Path) -> list[tuple[int, Path]]:
    candidates: list[tuple[int, Path]] = []
    for checkpoint_dir in raw_log_root.glob("*/checkpoints/*"):
        if checkpoint_dir.is_dir() and checkpoint_dir.name.isdigit():
            candidates.append((int(checkpoint_dir.name), checkpoint_dir))
    if not candidates:
        raise RuntimeError(f"Playground training completed without a checkpoint in {raw_log_root}")
    return sorted(candidates, key=lambda item: item[0])


def _archive_checkpoint(raw_checkpoint: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = shutil.make_archive(str(output.with_suffix("")), "zip", raw_checkpoint)
    archived = Path(temporary)
    if archived != output:
        archived.replace(output)
    return output


def _safe_extract_checkpoint(checkpoint: Path, destination: Path) -> None:
    with zipfile.ZipFile(checkpoint) as archive:
        root = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(root):
                raise RuntimeError(f"unsafe path in MJX checkpoint: {member.filename}")
        archive.extractall(destination)


def _repair_brax_checkpoint_config(checkpoint: Path) -> None:
    """Remove null initializer entries that Brax 0.14.2 cannot deserialize."""
    config_path = checkpoint / "ppo_network_config.json"
    if not config_path.is_file():
        return
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    network = raw.get("network_factory_kwargs")
    if not isinstance(network, dict):
        return
    changed = False
    for name in _BRAX_OPTIONAL_INITIALIZERS:
        if name in network and network[name] is None:
            del network[name]
            changed = True
    if changed:
        config_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _prepare_resume_checkpoint(
    checkpoint: Path,
    config: RunConfig,
    paths: RunPaths,
    *,
    allowed_source_environment: str | None = None,
) -> Path:
    if checkpoint.is_dir():
        return checkpoint
    metadata = load_checkpoint_metadata(checkpoint)
    if metadata.backend != config.backend or (
        metadata.environment != config.environment
        and metadata.environment != allowed_source_environment
    ):
        raise CheckpointError(
            f"checkpoint is for {metadata.backend}/{metadata.environment}, "
            f"not {config.backend}/{config.environment}"
        )
    if checkpoint.suffix != ".zip":
        raise RuntimeError(
            "MJX resume requires a raw Playground checkpoint directory or a zipped Orbax checkpoint"
        )
    destination = paths.root / "resume" / checkpoint.stem
    if destination.exists():
        shutil.rmtree(destination)
    # Playground's resume flag names a directory *containing* numeric
    # checkpoint directories.  An Orbax checkpoint archive contains the
    # contents of one numeric directory, including internal directories such
    # as ``ocdbt.process_0``.  Extracting it directly into ``destination``
    # therefore makes the upstream scanner try to parse those internal names
    # as checkpoint steps.  Restore the archive beneath its attested step so
    # the scanner sees exactly one numeric checkpoint entry.
    destination.mkdir(parents=True)
    _safe_extract_checkpoint(checkpoint, destination / f"{metadata.step:012d}")
    return destination


def _verify_brax_supported_tuple(checkpoint_root: Path, output: Path) -> dict[str, Any]:
    """Restore the pinned three-item Brax tuple in an isolated process."""
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "sim2policy.train_mjx",
            "--verify-brax-resume-worker",
            "--checkpoint-root",
            str(checkpoint_root),
            "--verification-output",
            str(output),
        ],
        check=True,
        text=True,
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    if result.get("restored_components") != [
        "observation_normalizer",
        "policy_parameters",
        "value_parameters",
    ]:
        raise RuntimeError("Brax checkpoint did not restore the supported PPO tuple")
    return result


def _verify_brax_supported_tuple_worker(checkpoint_root: Path, output: Path) -> None:
    children = sorted(
        (path for path in checkpoint_root.iterdir() if path.is_dir() and path.name.isdigit()),
        key=lambda path: int(path.name),
    )
    if not children:
        raise RuntimeError("resume root contains no numeric Brax checkpoint")
    checkpoint = children[-1]
    _repair_brax_checkpoint_config(checkpoint)
    ppo_checkpoint = importlib.import_module("brax.training.agents.ppo.checkpoint")
    restored = ppo_checkpoint.load(checkpoint)
    if not isinstance(restored, (tuple, list)) or len(restored) != 3:
        raise RuntimeError("pinned Brax PPO checkpoint is not a three-item supported tuple")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "brax_version": "0.14.2",
                "checkpoint_path": str(checkpoint),
                "restored_components": [
                    "observation_normalizer",
                    "policy_parameters",
                    "value_parameters",
                ],
                "reinitialized_components": [
                    "optimizer_state",
                    "learner_step",
                    "rollout_state",
                    "prng_state",
                ],
                "fresh_initialization_seed": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


@contextlib.contextmanager
def mjx_policy_session(
    checkpoint: Path,
    config: RunConfig,
    *,
    allowed_source_environment: str | None = None,
) -> Any:
    """Load a zipped Brax PPO policy and its matching Playground environment."""
    require_mjx()
    metadata = load_checkpoint_metadata(checkpoint)
    if metadata.backend != config.backend or (
        metadata.environment != config.environment
        and metadata.environment != allowed_source_environment
    ):
        raise CheckpointError(
            f"checkpoint is for {metadata.backend}/{metadata.environment}, "
            f"not {config.backend}/{config.environment}"
        )
    if is_g1_forward_environment(config.environment):
        register_g1_forward_environments()
    with tempfile.TemporaryDirectory(prefix="sim2policy-mjx-") as temporary:
        raw_checkpoint = Path(temporary) / checkpoint.stem
        raw_checkpoint.mkdir()
        _safe_extract_checkpoint(checkpoint, raw_checkpoint)
        _repair_brax_checkpoint_config(raw_checkpoint)
        try:
            load_policy = importlib.import_module("brax.training.agents.ppo.checkpoint").load_policy
            registry = importlib.import_module("mujoco_playground").registry
            jax = importlib.import_module("jax")
            policy = load_policy(raw_checkpoint, deterministic=True)
            environment = registry.load(
                config.environment, config_overrides=_environment_overrides(config)
            )
        except Exception as exc:
            raise RuntimeError(
                "MJX checkpoint restore failed. Use the pinned MJX image and a checkpoint "
                "created by the same Brax/Playground version matrix."
            ) from exc
        yield jax, environment, jax.jit(policy)


def fixed_forward_command_state(
    state: Any,
    environment: Any,
    jax: Any,
    *,
    target_velocity: float,
    horizon: int,
) -> Any:
    """Replace a joystick environment's random command with local-forward motion.

    Playground locomotion resets randomize both yaw and command. Gallery evaluation and
    media instead exercise the product's declared Walk Forward task, so the policy must
    observe one stable local-frame command for the complete rollout.
    """
    info = dict(state.info)
    if "command" not in info:
        raise RuntimeError("MJX locomotion environment has no joystick command contract")
    if bool(getattr(environment, "sim2policy_fixed_forward", False)):
        command = np.asarray(info["command"], dtype=float)
        if command.shape != (3,) or not np.allclose(command, [1.0, 0.0, 0.0]):
            raise RuntimeError("G1Forward environment violated its invariant command")
        return state
    command = jax.numpy.asarray(
        [target_velocity, 0.0, 0.0], dtype=info["command"].dtype
    )
    info["command"] = command
    if "steps_until_next_cmd" in info:
        info["steps_until_next_cmd"] = jax.numpy.asarray(
            horizon + 1, dtype=info["steps_until_next_cmd"].dtype
        )
    elif "step" in info:
        # Playground 0.2 G1 resamples after ``step > 500`` instead of using
        # Go1's countdown. A negative rollout-sized offset preserves the fixed
        # command without changing the pinned environment implementation.
        info["step"] = jax.numpy.asarray(
            -horizon, dtype=getattr(info["step"], "dtype", None)
        )
    else:
        raise RuntimeError("MJX locomotion environment has no command cadence contract")
    state = state.replace(info=info)
    observation_builder = getattr(environment, "_get_obs", None)
    if not callable(observation_builder):
        raise RuntimeError("MJX locomotion environment cannot refresh command observation")
    parameter_count = len(inspect.signature(observation_builder).parameters)
    if parameter_count == 2:
        observation = observation_builder(state.data, state.info)
    elif parameter_count == 3:
        sensor_ids = getattr(environment, "_feet_floor_found_sensor", None)
        model = getattr(environment, "_mj_model", None)
        if sensor_ids is None or model is None:
            raise RuntimeError("MJX locomotion environment cannot rebuild contact observation")
        contact = jax.numpy.asarray(
            [
                state.data.sensordata[model.sensor_adr[sensor_id]] > 0
                for sensor_id in sensor_ids
            ]
        )
        observation = observation_builder(state.data, state.info, contact)
    else:
        raise RuntimeError("MJX locomotion environment has an unsupported observation contract")
    return state.replace(obs=observation)


def local_forward_velocity(environment: Any, state: Any) -> float:
    """Return base velocity in the robot frame, independent of randomized start yaw."""
    velocity = getattr(environment, "get_local_linvel", None)
    if not callable(velocity):
        raise RuntimeError("MJX locomotion environment has no local velocity contract")
    if len(inspect.signature(velocity).parameters) == 1:
        local_velocity = velocity(state.data)
    else:
        # G1 exposes the same robot-frame quantity with an explicit body name.
        local_velocity = velocity(state.data, "pelvis")
    return float(local_velocity[0])


def classify_g1_termination(
    environment: Any, state: Any, *, terminated: bool
) -> tuple[str, tuple[str, ...]]:
    """Classify the exact pinned G1 done predicate without collapsing causes.

    The order is the reviewed primary-reason precedence.  Simultaneous sensor,
    orientation, and NaN causes remain in the returned tuple for diagnosis.
    """
    if not terminated:
        return "horizon", ("horizon",)

    causes: list[str] = []
    data = state.data
    if bool(np.isnan(np.asarray(data.qpos)).any()) or bool(
        np.isnan(np.asarray(data.qvel)).any()
    ):
        causes.append("nan_state")

    gravity = getattr(environment, "get_gravity", None)
    if callable(gravity) and float(np.asarray(gravity(data, "torso"))[-1]) < 0.0:
        causes.append("torso_inversion")

    model = getattr(environment, "_mj_model", None)
    sensor_data = np.asarray(data.sensordata)

    def active(attribute: str) -> bool:
        if model is None or not hasattr(environment, attribute):
            return False
        sensor_id = int(getattr(environment, attribute))
        return bool(sensor_data[int(model.sensor_adr[sensor_id])] > 0)

    if active("_right_foot_left_foot_found_sensor"):
        causes.append("foot_foot_contact")
    if active("_left_foot_right_shin_found_sensor") or active(
        "_right_foot_left_shin_found_sensor"
    ):
        causes.append("foot_shin_contact")
    if not causes:
        causes.append("unknown_environment_done")

    ordered = tuple(name for name in G1_TERMINATION_ORDER if name in causes)
    return ordered[0], ordered


def _create_initial_checkpoint(config: RunConfig, output_root: Path) -> Path:
    """Create the step-zero Brax policy checkpoint used for progression media."""
    require_mjx()
    if is_g1_forward_environment(config.environment):
        register_g1_forward_environments()
    jax = importlib.import_module("jax")
    registry = importlib.import_module("mujoco_playground").registry
    wrapper = importlib.import_module("mujoco_playground").wrapper
    playground_train = importlib.import_module("learning.train_jax_ppo")
    ppo = importlib.import_module("brax.training.agents.ppo.train")
    ppo_networks = importlib.import_module("brax.training.agents.ppo.networks")
    ppo_checkpoint = importlib.import_module("brax.training.agents.ppo.checkpoint")

    # Playground's get_rl_config reads its Abseil --impl flag. The initial-policy worker invokes
    # the library directly rather than through absl.app.run, so parse that one explicit setting
    # before accessing the config. This runs in a dedicated subprocess and cannot consume the
    # parent training command's arguments.
    _parse_initial_worker_flags(importlib.import_module("absl.flags").FLAGS, config)

    environment = registry.load(config.environment, config_overrides=_environment_overrides(config))
    ppo_params = playground_train.get_rl_config(upstream_environment(config.environment))
    hyperparameters = dict(config.training.hyperparameters)
    hyperparameters.pop("impl", None)
    hyperparameters.pop("playground_config_overrides", None)
    _apply_initial_hyperparameters(ppo_params, hyperparameters)
    ppo_params.num_timesteps = 0
    # Policy initialization is independent of rollout parallelism. One environment keeps the
    # step-zero snapshot cheap while preserving the exact observation/action/network contract.
    ppo_params.num_envs = 1
    network_factory = functools.partial(
        ppo_networks.make_ppo_networks, **ppo_params.network_factory
    )
    training_params = dict(ppo_params)
    training_params.pop("network_factory", None)
    num_eval_envs = training_params.pop("num_eval_envs", 1)
    make_policy, params, _ = ppo.train(
        environment=environment,
        network_factory=network_factory,
        seed=config.seed,
        wrap_env_fn=wrapper.wrap_for_brax_training,
        num_eval_envs=num_eval_envs,
        **training_params,
    )
    del make_policy
    network_config = ppo_checkpoint.network_config(
        observation_size=environment.observation_size,
        action_size=environment.action_size,
        normalize_observations=bool(ppo_params.normalize_observations),
        network_factory=network_factory,
    )
    ppo_checkpoint.save(output_root, 0, jax.device_get(params), network_config)
    return output_root / "000000000000"


def _apply_initial_hyperparameters(ppo_params: Any, hyperparameters: dict[str, Any]) -> None:
    """Apply CLI-equivalent overrides to Playground's direct initial-policy config."""
    for key, value in hyperparameters.items():
        if key in _NETWORK_FACTORY_HYPERPARAMETERS:
            setattr(ppo_params.network_factory, key, value)
        elif key != "network_factory":
            setattr(ppo_params, key, value)


def _parse_initial_worker_flags(flag_values: Any, config: RunConfig) -> None:
    if not flag_values.is_parsed():
        impl = str(config.training.hyperparameters.get("impl", "jax"))
        flag_values(["sim2policy-mjx-initial", f"--impl={impl}"])


def _create_initial_checkpoint_isolated(config: RunConfig, output_root: Path) -> Path:
    """Create the initial policy in a fresh process so its JAX GPU memory is released."""
    resolved_config = output_root.parent / "initial-policy-config.yaml"
    resolved_config.parent.mkdir(parents=True, exist_ok=True)
    resolved_config.write_text(config.to_yaml(), encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "sim2policy.train_mjx",
            "--initial-worker",
            "--config",
            str(resolved_config),
            "--initial-output",
            str(output_root),
        ],
        check=True,
        text=True,
    )
    checkpoint = output_root / "000000000000"
    if not checkpoint.is_dir():
        raise RuntimeError("MJX initial policy worker produced no step-zero checkpoint")
    return checkpoint


def train_mjx(
    config: RunConfig,
    run_id: str,
    runs_root: Path,
    resume: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    initial_checkpoint_factory: Callable[[RunConfig, Path], Path] | None = None,
    state: RunStateStore | None = None,
    allowed_source_environment: str | None = None,
    transition_record: dict[str, Any] | None = None,
) -> Path:
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    paths = create_run_paths(run_id, runs_root)
    store = ArtifactStore(config.storage, run_id)
    sampler = GpuSampler(interval_seconds=2.0).start()
    start_gpu = sampler.samples[0]
    phases: list[dict[str, Any]] = []
    phase_name: str | None = None
    phase_started_at = ""
    phase_started_monotonic = 0.0

    def transition(name: str | None) -> None:
        nonlocal phase_name, phase_started_at, phase_started_monotonic
        now = utc_now_iso()
        monotonic_now = time.monotonic()
        if phase_name is not None:
            phases.append(
                {
                    "name": phase_name,
                    "started_at": phase_started_at,
                    "completed_at": now,
                    "duration_seconds": monotonic_now - phase_started_monotonic,
                }
            )
        phase_name = name
        phase_started_at = now
        phase_started_monotonic = monotonic_now
        if name is not None:
            print(json.dumps({"event": "phase", "phase": name, "timestamp": now}), flush=True)

    def persist_telemetry(outcome: str, *, required: bool) -> None:
        transition(None)
        gpu_summary = sampler.stop()
        samples = sampler.samples
        output = write_runtime_record(
            paths.report / "runtime.json",
            runtime_record(
                started_at=started_at,
                completed_at=utc_now_iso(),
                runtime_seconds=time.monotonic() - started_monotonic,
                start_gpu=start_gpu,
                end_gpu=samples[-1],
                gpu_summary=gpu_summary,
                phases=phases,
                outcome=outcome,
            ),
        )
        if store.enabled:
            try:
                store.upload_file(output, "report/runtime.json")
            except Exception as exc:
                if required:
                    raise
                print(
                    json.dumps(
                        {"event": "telemetry_upload_failed", "error": type(exc).__name__}
                    ),
                    file=sys.stderr,
                    flush=True,
                )

    transition("environment_setup")
    try:
        environment_probe = validate_mjx_environment(config)
        jax_backend, devices = jax_device_info()
        print(
            json.dumps(
                {
                    "event": "jax_devices",
                    "backend": jax_backend,
                    "devices": devices,
                }
            ),
            flush=True,
        )
        require_accelerator(jax_backend, devices)
        if state is not None:
            state.update_status(
                STATUS_TRAINING,
                progress={"backend": config.backend, "environment": config.environment},
            )
        write_metadata(
            paths,
            run_id,
            config,
            {
                "requested": config.training.device,
                "mjx_environment": environment_probe,
                "jax_backend": jax_backend,
                "jax_devices": devices,
            },
        )
        raw_resume = (
            _prepare_resume_checkpoint(
                resume,
                config,
                paths,
                allowed_source_environment=allowed_source_environment,
            )
            if resume is not None
            else None
        )
        if transition_record is not None:
            if raw_resume is None or resume is None:
                raise RuntimeError("a G1 transition record requires a resume checkpoint")
            if config.seed != 0:
                raise RuntimeError("G1 transition requires fresh learner initialization at seed 0")
            expected_load_path = transition_record.get("restore", {}).get(
                "trainer_load_path"
            )
            if expected_load_path != str(raw_resume):
                raise RuntimeError("G1 transition trainer load path mismatch")
            parent = transition_record.get("parent", {})
            resume_metadata = load_checkpoint_metadata(resume)
            if (
                parent.get("checkpoint_name") != resume.name
                or parent.get("sidecar_step") != resume_metadata.step
                or parent.get("sha256") != resume_metadata.sha256
            ):
                raise RuntimeError("G1 transition parent mismatch before trainer load")
            restore_evidence = _verify_brax_supported_tuple(
                raw_resume, paths.report / "g1-restore-verification.json"
            )
            if store.enabled:
                store.upload_file(
                    paths.report / "g1-restore-verification.json",
                    "report/g1-restore-verification.json",
                )
            print(
                json.dumps({"event": "g1_resume_verified", **restore_evidence}),
                flush=True,
            )

        transition("initial_checkpoint")
        initial_raw_root = paths.root / "mjx_initial"
        initial_raw = (initial_checkpoint_factory or _create_initial_checkpoint_isolated)(
            config, initial_raw_root
        )
        initial = checkpoint_path(paths.checkpoints, "initial", 0)
        _archive_checkpoint(initial_raw, initial)
        write_checkpoint_metadata(initial, config, 0)
        if store.enabled:
            store.publish_checkpoint(initial, paths.root)

        transition("playground_compile_and_train")
        print(
            json.dumps(
                {
                    "event": "training_start",
                    "note": "the first evaluation includes XLA compilation and may be quiet",
                }
            ),
            flush=True,
        )
        command = build_playground_command(config, paths, resume=raw_resume)
        runner(command, check=True, text=True)

        transition("checkpoint_publish")
        raw_checkpoints = _playground_checkpoints(paths.root / "mjx_logs")
        archived_checkpoints: list[Path] = []
        final_step = raw_checkpoints[-1][0]
        for step, raw_checkpoint in raw_checkpoints:
            kind = "final" if step == final_step else "step"
            checkpoint = checkpoint_path(paths.checkpoints, kind, step)
            _archive_checkpoint(raw_checkpoint, checkpoint)
            write_checkpoint_metadata(checkpoint, config, step)
            archived_checkpoints.append(checkpoint)
            if store.enabled:
                store.publish_checkpoint(checkpoint, paths.root)
        final = archived_checkpoints[-1]

        transition("artifact_sync")
        store.sync_tree(paths.root, required=store.enabled)
        persist_telemetry("completed", required=True)
        if state is not None:
            manifest = state.discover_artifacts()
            if manifest:
                state.write_manifest(manifest)
            state.update_status(
                STATUS_TRAINING,
                progress={"latest_checkpoint": final.name, "trained_steps": final_step},
            )
        return final
    except BaseException:
        persist_telemetry("failed", required=False)
        raise


def evaluate_mjx(
    checkpoint: Path,
    config: RunConfig,
    *,
    seeds: list[int] | None = None,
    allowed_source_environment: str | None = None,
) -> tuple[list[dict[str, Any]], float]:
    episodes: list[dict[str, Any]] = []
    started = time.monotonic()
    episode_length = int(config.training.hyperparameters.get("episode_length", 1000))
    schedule = seeds or [
        config.evaluation.seeds[index % len(config.evaluation.seeds)]
        for index in range(config.evaluation.episodes)
    ]
    session_options = (
        {"allowed_source_environment": allowed_source_environment}
        if allowed_source_environment is not None
        else {}
    )
    with mjx_policy_session(checkpoint, config, **session_options) as (
        jax,
        environment,
        policy,
    ):
        reset = jax.jit(environment.reset)
        step = jax.jit(environment.step)
        for index, seed in enumerate(schedule):
            key = jax.random.PRNGKey(seed)
            state = fixed_forward_command_state(
                reset(key),
                environment,
                jax,
                target_velocity=config.success.target_velocity,
                horizon=episode_length,
            )
            reward_sum = 0.0
            velocities: list[float] = []
            terminated = False
            length = 0
            for episode_step in range(1, episode_length + 1):
                length = episode_step
                key, action_key = jax.random.split(key)
                action, _ = policy(state.obs, action_key)
                state = step(state, action)
                reward_sum += float(state.reward)
                velocities.append(local_forward_velocity(environment, state))
                if bool(state.done):
                    terminated = True
                    break
            if config.environment in {
                G1_FORWARD_FLAT_ENVIRONMENT,
                G1_FORWARD_ROUGH_ENVIRONMENT,
                "G1JoystickFlatTerrain",
                "G1JoystickRoughTerrain",
            }:
                termination_reason, termination_causes = classify_g1_termination(
                    environment, state, terminated=terminated
                )
            else:
                termination_reason = "fall" if terminated else "horizon"
                termination_causes = (termination_reason,)
            mean_velocity = sum(velocities) / len(velocities)
            success = mean_velocity >= float(config.success.min_velocity or 0)
            if config.success.require_not_fallen:
                success = success and not terminated
            episodes.append(
                {
                    "index": index,
                    "seed": seed,
                    "reward": reward_sum,
                    "length": length,
                    "horizon": episode_length,
                    "command_velocity": config.success.target_velocity,
                    "forward_velocity": velocities[-1],
                    "mean_velocity": mean_velocity,
                    # Kept for compatibility with the public aggregate schema;
                    # every non-horizon environment termination is a hard failure.
                    "fell": terminated,
                    "terminated": terminated,
                    "termination_reason": termination_reason,
                    "termination_causes": list(termination_causes),
                    "success": success,
                }
            )
    return episodes, time.monotonic() - started


def _override(value: str) -> tuple[str, Any]:
    return parse_override(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train an MJX/Playground PPO locomotion policy")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--resume", nargs="?", const="latest")
    parser.add_argument("--resume-run-id", help="Source run ID for --resume remote.")
    parser.add_argument("--set", action="append", default=[], type=_override, dest="overrides")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    from sim2policy.execution_location import require_nebius_execution

    require_nebius_execution("training")
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if "--initial-worker" in raw_args:
        worker = argparse.ArgumentParser()
        worker.add_argument("--initial-worker", action="store_true")
        worker.add_argument("--config", required=True)
        worker.add_argument("--initial-output", required=True, type=Path)
        worker_args = worker.parse_args(raw_args)
        _create_initial_checkpoint(load_config(worker_args.config), worker_args.initial_output)
        return
    if "--verify-brax-resume-worker" in raw_args:
        worker = argparse.ArgumentParser()
        worker.add_argument("--verify-brax-resume-worker", action="store_true")
        worker.add_argument("--checkpoint-root", required=True, type=Path)
        worker.add_argument("--verification-output", required=True, type=Path)
        worker_args = worker.parse_args(raw_args)
        _verify_brax_supported_tuple_worker(
            worker_args.checkpoint_root, worker_args.verification_output
        )
        return
    args = build_parser().parse_args(raw_args)
    config = load_config(args.config, dict(args.overrides))
    if config.backend != "mjx":
        raise SystemExit("selected config is not an MJX config")
    resume = None
    allowed_source_environment = next(
        (
            source
            for source, target in REVIEWED_RESUME_TRANSITIONS
            if target == config.environment
        ),
        None,
    )
    if args.resume:
        if args.resume == "remote":
            paths = create_run_paths(args.run_id, args.runs_root)
            resume = ArtifactStore(config.storage, args.resume_run_id or args.run_id).resume_latest(
                paths.checkpoints,
                config,
                allowed_source_environment=allowed_source_environment,
            )
        else:
            resume = (
                latest_checkpoint(args.runs_root / args.run_id / "checkpoints")
                if args.resume == "latest"
                else Path(args.resume)
            )
    state = RunStateStore(config.storage, args.run_id, args.runs_root)
    try:
        final = train_mjx(
            config,
            args.run_id,
            args.runs_root,
            resume=resume,
            state=state,
            allowed_source_environment=allowed_source_environment,
        )
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        state.update_status(STATUS_FAILED, error=str(exc))
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps({"status": "complete", "checkpoint": str(final)}))


if __name__ == "__main__":
    main()
