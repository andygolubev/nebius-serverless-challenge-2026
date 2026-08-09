"""Scene geometry a locomotion task must fit inside.

A Playground locomotion scene is either an unbounded ``type="plane"`` floor or a
finite height field.  A finite field has an edge, and past that edge there is no
supporting geometry at all, so a robot commanded to walk forward for the whole
episode falls off the world rather than failing at the task.

The pinned upstream G1 rough field is 20 m x 20 m with the robot spawning dead
centre, which leaves 10 m to the nearest edge.  A 1,000-step episode at 0.02 s
per step commanded at 0.8 m/s implies 16 m of travel, so the published gate
could not be met by any policy.  :func:`check_scene_extent` turns that class of
mistake into a validation error instead of a paid GPU run.

This module stays free of MuJoCo and MJX imports so the SB3-only install keeps
working; the numbers below are the reviewed properties of the registered scenes
and are asserted against the real models in the MJX test suite.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

UNBOUNDED = None


class SceneExtentError(ValueError):
    """Raised when a configured task cannot fit inside its scene."""


@dataclass(frozen=True)
class SceneExtent:
    """The supporting geometry of one registered locomotion scene.

    ``half_extent_m`` is ``None`` for an unbounded plane.  For a square height
    field it is the distance from the centre to an axis-aligned edge, which is
    also the worst case over spawn yaws.
    """

    identity: str
    half_extent_m: float | None
    ctrl_dt: float
    cells_per_side: int | None = None
    elevation_amplitude_m: float | None = None

    @property
    def bounded(self) -> bool:
        return self.half_extent_m is not None

    @property
    def resolution_m(self) -> float | None:
        """Metres per height-field cell, the measure of terrain difficulty."""
        if self.half_extent_m is None or self.cells_per_side is None:
            return None
        return 2.0 * self.half_extent_m / self.cells_per_side

    def worst_case_spawn_to_edge_m(self) -> float | None:
        """Shortest distance from the spawn point to the edge over all yaws.

        Playground's G1 reset randomizes yaw but never ``qpos[0:2]``, so the
        robot always starts at the centre.  Travelling along yaw ``t`` reaches
        the boundary of a square field at ``half / max(|cos t|, |sin t|)``,
        which is smallest -- exactly ``half`` -- for an axis-aligned heading.
        """
        return self.half_extent_m

    def best_case_spawn_to_edge_m(self) -> float | None:
        """Longest such distance, reached on a diagonal heading."""
        if self.half_extent_m is None:
            return None
        return self.half_extent_m * math.sqrt(2.0)


# Half-extents are the reviewed geometry of each registered scene. The G1 rough
# entry is the server-owned enlarged field registered by
# ``g1_forward_env.register_g1_forward_environments``; every other entry is the
# pinned upstream scene.
SCENE_EXTENTS: dict[str, SceneExtent] = {
    # Upstream ``scene_mjx_feetonly_flat_terrain.xml``: ``size="0 0 0.01"`` plane.
    "G1ForwardFlatTerrain": SceneExtent(
        identity="playground/g1/scene_mjx_feetonly_flat_terrain.xml",
        half_extent_m=UNBOUNDED,
        ctrl_dt=0.02,
    ),
    "G1JoystickFlatTerrain": SceneExtent(
        identity="playground/g1/scene_mjx_feetonly_flat_terrain.xml",
        half_extent_m=UNBOUNDED,
        ctrl_dt=0.02,
    ),
    # Server-owned enlarged field: upstream 256x256 tiled 3x3 at the upstream
    # 7.8125 cm/cell resolution and 0.05 m amplitude.
    "G1ForwardRoughTerrain": SceneExtent(
        identity="sim2policy/scenes/g1_rough_terrain_60m.xml",
        half_extent_m=30.0,
        ctrl_dt=0.02,
        cells_per_side=768,
        elevation_amplitude_m=0.05,
    ),
    # Upstream ``scene_mjx_feetonly_rough_terrain.xml``: ``size="10 10 .05 1.0"``.
    # Retained unchanged so the published recording stays comparable.
    "G1JoystickRoughTerrain": SceneExtent(
        identity="playground/g1/scene_mjx_feetonly_rough_terrain.xml",
        half_extent_m=10.0,
        ctrl_dt=0.02,
        cells_per_side=256,
        elevation_amplitude_m=0.05,
    ),
    # Upstream ``scene_mjx_feetonly_flat_terrain.xml``: ``size="0 0 0.01"`` plane.
    "Go1JoystickFlatTerrain": SceneExtent(
        identity="playground/go1/scene_mjx_feetonly_flat_terrain.xml",
        half_extent_m=UNBOUNDED,
        ctrl_dt=0.02,
    ),
}

# The enlarged G1 rough field, as registered. Kept next to the extent table so
# the scene builder and the validator cannot drift apart.
G1_ROUGH_SCENE_FILE = "g1_rough_terrain_60m.xml"
G1_ROUGH_TILE_FACTOR = 3
G1_ROUGH_UPSTREAM_CELLS = 256
G1_ROUGH_CELLS = G1_ROUGH_UPSTREAM_CELLS * G1_ROUGH_TILE_FACTOR
G1_ROUGH_HALF_EXTENT_M = 30.0
G1_ROUGH_ELEVATION_M = 0.05


def scene_extent(environment: str) -> SceneExtent | None:
    """Return the reviewed scene extent for an environment, if one is known."""
    return SCENE_EXTENTS.get(environment)


def implied_travel_m(target_velocity: float, episode_length: int, ctrl_dt: float) -> float:
    """Distance the commanded velocity implies over a full episode."""
    return float(target_velocity) * int(episode_length) * float(ctrl_dt)


def max_command_for_scene(extent: SceneExtent, episode_length: int) -> float | None:
    """Fastest command whose full episode still fits, worst-case yaw."""
    available = extent.worst_case_spawn_to_edge_m()
    if available is None:
        return None
    return available / (int(episode_length) * extent.ctrl_dt)


def check_scene_extent(
    environment: str, *, target_velocity: float, episode_length: int
) -> None:
    """Reject a task whose commanded travel does not fit inside its scene.

    Unknown environments and unbounded scenes pass. A bounded scene must contain
    the implied travel along *every* spawn yaw, so the worst-case axis-aligned
    distance is the bar.
    """
    extent = scene_extent(environment)
    if extent is None or not extent.bounded:
        return
    available = extent.worst_case_spawn_to_edge_m()
    assert available is not None  # bounded implies a half extent
    required = implied_travel_m(target_velocity, episode_length, extent.ctrl_dt)
    if required <= available:
        return
    fastest = max_command_for_scene(extent, episode_length)
    assert fastest is not None
    raise SceneExtentError(
        f"{environment} commands {target_velocity:g} m/s for {episode_length} steps "
        f"({required:.2f} m of travel) but its scene supports only {available:.2f} m "
        f"from the spawn point on the worst-case heading "
        f"(scene {extent.identity}, half extent {extent.half_extent_m:g} m). "
        f"The gate is unreachable by any policy; the fastest command that fits is "
        f"{fastest:.3f} m/s."
    )
