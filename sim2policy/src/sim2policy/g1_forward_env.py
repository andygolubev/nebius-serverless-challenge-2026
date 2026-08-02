"""Fixed-forward G1 environment identities over pinned Playground v0.2.0.

The public task is Walk Forward, while Playground's upstream G1 joystick task
samples lateral/yaw commands and periodically replaces them.  These server-owned
identities change only that command source and disable pushes; every other
environment and training contract remains the pinned upstream implementation.

Imports stay inside :func:`register_g1_forward_environments` so the base
Sim2Policy package remains importable without the optional MJX dependencies.
"""

from __future__ import annotations

import functools
import importlib
import importlib.metadata
from typing import Any


G1_FORWARD_FLAT_ENVIRONMENT = "G1ForwardFlatTerrain"
G1_FORWARD_ROUGH_ENVIRONMENT = "G1ForwardRoughTerrain"
G1_FORWARD_COMMAND = (1.0, 0.0, 0.0)
PINNED_PLAYGROUND_VERSION = "0.2.0"

SOURCE_ENVIRONMENTS = {
    G1_FORWARD_FLAT_ENVIRONMENT: "G1JoystickFlatTerrain",
    G1_FORWARD_ROUGH_ENVIRONMENT: "G1JoystickRoughTerrain",
}


def upstream_environment(environment: str) -> str:
    """Return the pinned upstream identity that supplies an environment's PPO config."""
    return SOURCE_ENVIRONMENTS.get(environment, environment)


def is_g1_forward_environment(environment: str) -> bool:
    return environment in SOURCE_ENVIRONMENTS


def register_g1_forward_environments() -> None:
    """Idempotently register fixed-forward G1 flat and rough environments."""
    try:
        version = importlib.metadata.version("mujoco-playground")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("mujoco-playground is unavailable") from exc
    if version != PINNED_PLAYGROUND_VERSION:
        raise RuntimeError(
            "fixed-forward G1 requires pinned mujoco-playground "
            f"{PINNED_PLAYGROUND_VERSION}, found {version}"
        )

    locomotion = importlib.import_module("mujoco_playground._src.locomotion")
    joystick = importlib.import_module(
        "mujoco_playground._src.locomotion.g1.joystick"
    )
    jax_numpy = importlib.import_module("jax.numpy")

    class ForwardJoystick(joystick.Joystick):  # type: ignore[misc, valid-type]
        """Pinned G1 joystick physics with one invariant local-forward command."""

        sim2policy_fixed_forward = True

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            if bool(self._config.push_config.enable):
                raise ValueError("G1Forward environments require pushes disabled")

        def sample_command(self, rng: Any) -> Any:
            del rng
            return jax_numpy.asarray(G1_FORWARD_COMMAND)

    def default_config() -> Any:
        config = joystick.default_config()
        config.push_config.enable = False
        return config

    for name, task in (
        (G1_FORWARD_FLAT_ENVIRONMENT, "flat_terrain"),
        (G1_FORWARD_ROUGH_ENVIRONMENT, "rough_terrain"),
    ):
        if name not in locomotion.ALL_ENVS:
            locomotion.register_environment(
                name,
                functools.partial(ForwardJoystick, task=task),
                default_config,
            )
        # Registration's public API does not expose randomizers. Preserve the
        # upstream G1 randomizer exactly instead of silently dropping it.
        locomotion._randomizer[name] = locomotion._randomizer[SOURCE_ENVIRONMENTS[name]]
