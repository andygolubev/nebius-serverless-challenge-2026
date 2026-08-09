"""Fixed-forward G1 environment identities over pinned Playground v0.2.0.

The public task is Walk Forward, while Playground's upstream G1 joystick task
samples lateral/yaw commands and periodically replaces them.  These server-owned
identities change only that command source, disable pushes, and -- for rough
terrain -- enlarge the height field so the commanded task fits inside the scene;
every other environment and training contract remains the pinned upstream
implementation.

Upstream's rough scene is a finite 20 m x 20 m height field with no floor beyond
it, and Playground's reset randomizes yaw but never ``qpos[0:2]``, so the robot
always starts 10 m from the nearest edge.  A 1,000-step episode at 0.02 s
commanded at 0.8 m/s implies 16 m of travel, which made the rough acceptance gate
unreachable by any policy.  The server-owned scene tiles the upstream height
field 3x3 at identical resolution and amplitude, so the extent grows while
per-step terrain difficulty is unchanged.

Imports stay inside :func:`register_g1_forward_environments` so the base
Sim2Policy package remains importable without the optional MJX dependencies.
"""

from __future__ import annotations

import functools
import importlib
import importlib.metadata
from importlib import resources
from typing import Any

from .locomotion_scene import (
    G1_ROUGH_CELLS,
    G1_ROUGH_HALF_EXTENT_M,
    G1_ROUGH_SCENE_FILE,
    G1_ROUGH_TILE_FACTOR,
    G1_ROUGH_UPSTREAM_CELLS,
)

G1_FORWARD_FLAT_ENVIRONMENT = "G1ForwardFlatTerrain"
G1_FORWARD_ROUGH_ENVIRONMENT = "G1ForwardRoughTerrain"
G1_FORWARD_FLAT_COMMAND = (1.0, 0.0, 0.0)
G1_FORWARD_ROUGH_COMMAND = (0.8, 0.0, 0.0)
G1_FORWARD_COMMANDS = {
    G1_FORWARD_FLAT_ENVIRONMENT: G1_FORWARD_FLAT_COMMAND,
    G1_FORWARD_ROUGH_ENVIRONMENT: G1_FORWARD_ROUGH_COMMAND,
}
PINNED_PLAYGROUND_VERSION = "0.2.0"

SOURCE_ENVIRONMENTS = {
    G1_FORWARD_FLAT_ENVIRONMENT: "G1JoystickFlatTerrain",
    G1_FORWARD_ROUGH_ENVIRONMENT: "G1JoystickRoughTerrain",
}


def rough_scene_path() -> Any:
    """Return the packaged server-owned rough-terrain scene."""
    return resources.files("sim2policy").joinpath("scenes", G1_ROUGH_SCENE_FILE)


def tiled_rough_hfield(upstream_png: bytes) -> Any:
    """Tile the pinned upstream height field into the enlarged server-owned field.

    Returns a ``(768, 768)`` float array normalized to ``[0, 1]``, which is the
    layout MuJoCo expects in ``model.hfield_data``.  Tiling -- rather than
    stretching the same 256x256 asset over a larger ``size`` -- is what keeps
    metres-per-cell and the elevation amplitude identical to upstream, so the
    terrain is no easier per step than the field this replaces.
    """
    import io

    import numpy as np
    from PIL import Image

    image = np.asarray(Image.open(io.BytesIO(upstream_png)))
    if image.ndim == 3:
        if not (
            np.array_equal(image[..., 0], image[..., 1])
            and np.array_equal(image[..., 0], image[..., 2])
        ):
            raise RuntimeError("upstream G1 height field is not single-valued across channels")
        image = image[..., 0]
    if image.shape != (G1_ROUGH_UPSTREAM_CELLS, G1_ROUGH_UPSTREAM_CELLS):
        raise RuntimeError(
            "upstream G1 height field is "
            f"{image.shape}, expected "
            f"({G1_ROUGH_UPSTREAM_CELLS}, {G1_ROUGH_UPSTREAM_CELLS})"
        )
    tiled = np.tile(image.astype(np.float64) / 255.0, (G1_ROUGH_TILE_FACTOR, G1_ROUGH_TILE_FACTOR))
    if tiled.shape != (G1_ROUGH_CELLS, G1_ROUGH_CELLS):
        raise RuntimeError("tiled G1 height field has the wrong shape")
    return tiled


def upstream_environment(environment: str) -> str:
    """Return the pinned upstream identity that supplies an environment's PPO config."""
    return SOURCE_ENVIRONMENTS.get(environment, environment)


def is_g1_forward_environment(environment: str) -> bool:
    return environment in SOURCE_ENVIRONMENTS


def forward_command(environment: str) -> tuple[float, float, float]:
    """Return the reviewed invariant command for one fixed-forward identity."""
    try:
        return G1_FORWARD_COMMANDS[environment]
    except KeyError as exc:
        raise ValueError(f"unsupported fixed-forward environment: {environment}") from exc


def register_g1_forward_environments() -> None:
    """Idempotently register fixed-forward G1 flat and rough environments."""
    try:
        version = importlib.metadata.version("playground")
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
    g1_base = importlib.import_module("mujoco_playground._src.locomotion.g1.base")
    g1_constants = importlib.import_module(
        "mujoco_playground._src.locomotion.g1.g1_constants"
    )
    jax_numpy = importlib.import_module("jax.numpy")
    mjx = importlib.import_module("mujoco.mjx")

    class ForwardJoystick(joystick.Joystick):  # type: ignore[misc, name-defined]
        """Pinned G1 joystick physics with one invariant local-forward command."""

        sim2policy_fixed_forward = True

        def __init__(
            self,
            *args: Any,
            sim2policy_forward_command: tuple[float, float, float],
            **kwargs: Any,
        ) -> None:
            self.sim2policy_forward_command = sim2policy_forward_command
            super().__init__(*args, **kwargs)
            if bool(self._config.push_config.enable):
                raise ValueError("G1Forward environments require pushes disabled")

        def sample_command(self, rng: Any) -> Any:
            del rng
            return jax_numpy.asarray(self.sim2policy_forward_command)

    class ForwardRoughJoystick(ForwardJoystick):  # type: ignore[misc, valid-type]
        """Fixed-forward G1 on the server-owned enlarged rough-terrain field.

        ``Joystick.__init__`` hardcodes ``consts.task_to_xml(task)``, so the
        repo-owned scene cannot be threaded through it.  This calls the pinned
        ``G1Env.__init__`` with our scene, fills the height field that the scene
        declares by ``nrow``/``ncol``, then reapplies the base class's post-load
        model settings and re-publishes the model to MJX.  Playground stays
        pinned and unmodified on disk.
        """

        sim2policy_rough_scene = True
        sim2policy_rough_half_extent_m = G1_ROUGH_HALF_EXTENT_M

        def __init__(
            self,
            *,
            sim2policy_forward_command: tuple[float, float, float],
            config: Any,
            config_overrides: Any = None,
            task: str | None = None,
        ) -> None:
            del task  # this identity is always the server-owned rough scene
            self.sim2policy_forward_command = sim2policy_forward_command
            g1_base.G1Env.__init__(
                self,
                xml_path=rough_scene_path().as_posix(),
                config=config,
                config_overrides=config_overrides,
            )
            if bool(self._config.push_config.enable):
                raise ValueError("G1Forward environments require pushes disabled")
            self._sim2policy_fill_rough_hfield()
            self._post_init()

        def _sim2policy_fill_rough_hfield(self) -> None:
            model = self._mj_model
            if int(model.nhfield) != 1:
                raise RuntimeError("server-owned G1 rough scene must declare one height field")
            if (int(model.hfield_nrow[0]), int(model.hfield_ncol[0])) != (
                G1_ROUGH_CELLS,
                G1_ROUGH_CELLS,
            ):
                raise RuntimeError("server-owned G1 rough scene has the wrong height-field size")
            upstream_png = (
                g1_constants.ROOT_PATH / "xmls" / "assets" / "hfield.png"
            ).read_bytes()
            model.hfield_data[:] = tiled_rough_hfield(upstream_png).ravel()
            # ``G1Env.__init__`` applied these before we replaced the field; the
            # model object is the same, so only the MJX copy must be refreshed.
            self._mjx_model = mjx.put_model(model, impl=self._config.impl)

    def default_config() -> Any:
        config = joystick.default_config()
        config.push_config.enable = False
        return config

    for name, task, command, factory in (
        (
            G1_FORWARD_FLAT_ENVIRONMENT,
            "flat_terrain",
            G1_FORWARD_FLAT_COMMAND,
            ForwardJoystick,
        ),
        (
            G1_FORWARD_ROUGH_ENVIRONMENT,
            "rough_terrain",
            G1_FORWARD_ROUGH_COMMAND,
            ForwardRoughJoystick,
        ),
    ):
        if name not in locomotion.ALL_ENVS:
            locomotion.register_environment(
                name,
                functools.partial(
                    factory,
                    task=task,
                    sim2policy_forward_command=command,
                ),
                default_config,
            )
        # Registration's public API does not expose randomizers. Preserve the
        # upstream G1 randomizer exactly instead of silently dropping it.
        locomotion._randomizer[name] = locomotion._randomizer[SOURCE_ENVIRONMENTS[name]]
