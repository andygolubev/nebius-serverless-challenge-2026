"""Bounded container gate for every server-owned gallery environment."""

from __future__ import annotations

import argparse
import importlib
import math
from pathlib import Path

from sim2policy.config import load_config

ROOT = Path("/app")
SB3_CONFIGS = (
    "ant_gallery_sb3.yaml",
    "halfcheetah_gallery_sb3.yaml",
    "hopper_sb3.yaml",
    "walker2d_sb3.yaml",
    "reacher_sb3.yaml",
)
MJX_CONFIGS = ("go1_mjx.yaml", "g1_mjx.yaml")


def smoke_sb3() -> None:
    import gymnasium as gym

    from sim2policy.render import _make_rgb_env

    for name in SB3_CONFIGS:
        config = load_config(ROOT / "configs" / name)
        env = _make_rgb_env(gym, config)
        try:
            observation, _ = env.reset(seed=config.seed)
            observation, reward, _, _, _ = env.step(env.action_space.sample())
            frame = env.render()
            if frame is None or frame.ndim != 3 or not math.isfinite(float(reward)):
                raise RuntimeError(f"SB3 gallery environment smoke failed: {name}")
            if observation.shape != env.observation_space.shape:
                raise RuntimeError(f"SB3 gallery observation mismatch: {name}")
            print(f"gallery environment ok: {name} {frame.shape}")
        finally:
            env.close()


def smoke_mjx() -> None:
    import jax
    from mujoco_playground import registry

    from sim2policy.train_mjx import (
        _NETWORK_FACTORY_HYPERPARAMETERS,
        _apply_initial_hyperparameters,
        _parse_initial_worker_flags,
        fixed_forward_command_state,
        local_forward_velocity,
        validate_mjx_environment,
    )

    # Importing Playground's CLI module defines the Abseil flags consumed by
    # get_rl_config. Match the initial-policy worker's production import order.
    playground_train = importlib.import_module("learning.train_jax_ppo")

    for name in MJX_CONFIGS:
        config = load_config(ROOT / "configs" / name)
        _parse_initial_worker_flags(importlib.import_module("absl.flags").FLAGS, config)
        ppo_params = playground_train.get_rl_config(config.environment)
        hyperparameters = dict(config.training.hyperparameters)
        hyperparameters.pop("impl", None)
        _apply_initial_hyperparameters(ppo_params, hyperparameters)
        for key in _NETWORK_FACTORY_HYPERPARAMETERS & hyperparameters.keys():
            if (
                key in ppo_params
                or getattr(ppo_params.network_factory, key) != hyperparameters[key]
            ):
                raise RuntimeError(f"MJX initial-policy network contract failed: {name} {key}")
        probe = validate_mjx_environment(config)
        if not probe.get("observation_size") or not probe.get("action_size"):
            raise RuntimeError(f"MJX gallery environment smoke failed: {name}")
        environment = registry.load(
            config.environment,
            config_overrides={"impl": config.training.hyperparameters.get("impl", "jax")},
        )
        state = fixed_forward_command_state(
            environment.reset(jax.random.PRNGKey(config.seed)),
            environment,
            jax,
            target_velocity=config.success.target_velocity,
            horizon=config.rendering.frames,
        )
        velocity = local_forward_velocity(environment, state)
        if not math.isfinite(velocity):
            raise RuntimeError(f"MJX gallery locomotion contract failed: {name}")
        print(f"gallery environment ok: {name} {probe} local_velocity={velocity:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("sb3", "mjx"), required=True)
    args = parser.parse_args()
    smoke_sb3() if args.backend == "sb3" else smoke_mjx()


if __name__ == "__main__":
    main()
