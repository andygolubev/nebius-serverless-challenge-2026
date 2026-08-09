from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from sim2policy.config import ConfigError, load_config
from sim2policy.g1_forward_env import rough_scene_path, tiled_rough_hfield
from sim2policy.locomotion_scene import (
    G1_ROUGH_CELLS,
    G1_ROUGH_ELEVATION_M,
    G1_ROUGH_HALF_EXTENT_M,
    G1_ROUGH_UPSTREAM_CELLS,
    SCENE_EXTENTS,
    SceneExtent,
    SceneExtentError,
    check_scene_extent,
    implied_travel_m,
    max_command_for_scene,
    scene_extent,
)

ROOT = Path(__file__).parents[1]
UPSTREAM_ROUGH_HALF_EXTENT_M = 10.0
UPSTREAM_RESOLUTION_M = 2 * UPSTREAM_ROUGH_HALF_EXTENT_M / G1_ROUGH_UPSTREAM_CELLS


def test_implied_travel_is_command_times_wall_clock_horizon() -> None:
    assert implied_travel_m(0.8, 1000, 0.02) == pytest.approx(16.0)
    assert implied_travel_m(1.0, 1000, 0.02) == pytest.approx(20.0)


def test_square_field_worst_case_is_axis_aligned_and_best_case_diagonal() -> None:
    extent = scene_extent("G1ForwardRoughTerrain")
    assert extent is not None
    assert extent.worst_case_spawn_to_edge_m() == pytest.approx(30.0)
    assert extent.best_case_spawn_to_edge_m() == pytest.approx(30.0 * math.sqrt(2))


def test_unbounded_plane_accepts_any_command() -> None:
    for environment in ("G1ForwardFlatTerrain", "G1JoystickFlatTerrain", "Go1JoystickFlatTerrain"):
        extent = scene_extent(environment)
        assert extent is not None and not extent.bounded
        assert max_command_for_scene(extent, 1000) is None
        check_scene_extent(environment, target_velocity=5.0, episode_length=100_000)


def test_upstream_rough_field_cannot_hold_the_published_gate() -> None:
    """The exact defect this scene change exists to fix."""
    with pytest.raises(SceneExtentError) as excinfo:
        check_scene_extent("G1JoystickRoughTerrain", target_velocity=0.8, episode_length=1000)
    message = str(excinfo.value)
    assert "16.00 m" in message  # implied travel
    assert "10.00 m" in message  # available distance
    assert "0.500 m/s" in message  # fastest command that fits


def test_enlarged_rough_field_holds_the_gate_with_margin() -> None:
    check_scene_extent("G1ForwardRoughTerrain", target_velocity=0.8, episode_length=1000)
    extent = scene_extent("G1ForwardRoughTerrain")
    assert extent is not None
    fastest = max_command_for_scene(extent, 1000)
    assert fastest is not None and fastest == pytest.approx(1.5)


def test_enlarged_field_is_rejected_once_the_command_outgrows_it() -> None:
    with pytest.raises(SceneExtentError):
        check_scene_extent("G1ForwardRoughTerrain", target_velocity=1.6, episode_length=1000)


def test_unknown_environment_is_not_silently_constrained() -> None:
    assert scene_extent("SomeFutureEnvironment") is None
    check_scene_extent("SomeFutureEnvironment", target_velocity=9.0, episode_length=1000)


def test_enlarged_field_preserves_upstream_resolution_and_amplitude() -> None:
    """Growing the extent must not quietly make the terrain easier."""
    enlarged = scene_extent("G1ForwardRoughTerrain")
    upstream = scene_extent("G1JoystickRoughTerrain")
    assert enlarged is not None and upstream is not None
    assert upstream.resolution_m == pytest.approx(UPSTREAM_RESOLUTION_M)
    assert enlarged.resolution_m == pytest.approx(upstream.resolution_m)
    assert enlarged.elevation_amplitude_m == upstream.elevation_amplitude_m
    assert enlarged.half_extent_m == G1_ROUGH_HALF_EXTENT_M
    assert enlarged.cells_per_side == G1_ROUGH_CELLS


def test_every_configured_mjx_environment_declares_a_scene_extent() -> None:
    """A new MJX config cannot slip past the invariant by being unlisted."""
    for path in sorted((ROOT / "configs").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict) or raw.get("backend") != "mjx":
            continue
        environment = raw["environment"]
        assert environment in SCENE_EXTENTS, f"{path.name} uses unlisted environment {environment}"


def test_shipped_mjx_configs_all_fit_their_scenes() -> None:
    for path in sorted((ROOT / "configs").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict) or raw.get("backend") != "mjx":
            continue
        load_config(path)


def test_config_validation_rejects_a_task_that_cannot_fit() -> None:
    with pytest.raises(ConfigError, match="unreachable by any policy"):
        load_config(
            ROOT / "configs/g1_forward_rough_mjx.yaml",
            {"success.target_velocity": 2.0},
        )


def test_scene_extent_resolution_is_none_when_unbounded() -> None:
    extent = SceneExtent(identity="plane", half_extent_m=None, ctrl_dt=0.02)
    assert extent.resolution_m is None
    assert extent.best_case_spawn_to_edge_m() is None


def test_packaged_rough_scene_declares_the_enlarged_field() -> None:
    scene = rough_scene_path().read_text()
    hfield = next(line for line in scene.splitlines() if "<hfield" in line)
    assert f'nrow="{G1_ROUGH_CELLS}" ncol="{G1_ROUGH_CELLS}"' in hfield
    assert f'size="{G1_ROUGH_HALF_EXTENT_M:g} {G1_ROUGH_HALF_EXTENT_M:g} .05 1.0"' in hfield
    # The field is filled at registration, never loaded from an asset file.
    assert "file=" not in hfield
    # Everything else stays the upstream scene.
    assert '<include file="g1_mjx_feetonly.xml"/>' in scene
    assert '<geom name="floor" type="hfield" hfield="hfield" material="groundplane"/>' in scene
    assert 'name="knees_bent"' in scene


def test_tiling_repeats_the_upstream_field_without_resampling() -> None:
    import numpy as np

    rng = np.random.default_rng(0)
    source = rng.random((G1_ROUGH_UPSTREAM_CELLS, G1_ROUGH_UPSTREAM_CELLS))
    tiled = tiled_rough_hfield(source)

    assert tiled.shape == (G1_ROUGH_CELLS, G1_ROUGH_CELLS)
    for row in range(3):
        for column in range(3):
            block = tiled[
                row * G1_ROUGH_UPSTREAM_CELLS : (row + 1) * G1_ROUGH_UPSTREAM_CELLS,
                column * G1_ROUGH_UPSTREAM_CELLS : (column + 1) * G1_ROUGH_UPSTREAM_CELLS,
            ]
            np.testing.assert_allclose(block, source)
    # Every value in the enlarged field came from the reviewed upstream field:
    # tiling never resamples, interpolates, or rescales.
    assert set(np.unique(tiled).tolist()) == set(np.unique(source).tolist())


def test_tiling_rejects_an_unexpected_upstream_field() -> None:
    import numpy as np

    with pytest.raises(RuntimeError, match="expected"):
        tiled_rough_hfield(np.zeros((128, 128)))


def test_elevation_amplitude_is_carried_by_the_scene_not_the_tiling() -> None:
    """Tiling is unit-free; amplitude lives in the scene's ``size`` attribute."""
    assert G1_ROUGH_ELEVATION_M == 0.05
    assert '.05 1.0"' in rough_scene_path().read_text()
