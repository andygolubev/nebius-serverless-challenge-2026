from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from sim2policy.config import load_config
from sim2policy.g1_forward_env import (
    G1_FORWARD_FLAT_COMMAND,
    G1_FORWARD_FLAT_ENVIRONMENT,
    G1_FORWARD_ROUGH_COMMAND,
    G1_FORWARD_ROUGH_ENVIRONMENT,
    forward_command,
    register_g1_forward_environments,
    upstream_environment,
)
from sim2policy.locomotion_scene import (
    G1_ROUGH_CELLS,
    G1_ROUGH_HALF_EXTENT_M,
    G1_ROUGH_TILE_FACTOR,
)

ROOT = Path(__file__).parents[1]


def test_forward_identities_map_only_ppo_lookup_to_pinned_upstream_g1() -> None:
    assert upstream_environment(G1_FORWARD_FLAT_ENVIRONMENT) == "G1JoystickFlatTerrain"
    assert upstream_environment(G1_FORWARD_ROUGH_ENVIRONMENT) == "G1JoystickRoughTerrain"
    assert upstream_environment("Go1JoystickFlatTerrain") == "Go1JoystickFlatTerrain"


@pytest.mark.skipif(
    importlib.util.find_spec("mujoco_playground") is None,
    reason="MJX dependencies are exercised in the pinned Nebius image",
)
def test_fixed_forward_environment_preserves_upstream_contract() -> None:
    register_g1_forward_environments()
    from mujoco_playground._src import locomotion

    for forward, upstream, command in (
        (G1_FORWARD_FLAT_ENVIRONMENT, "G1JoystickFlatTerrain", G1_FORWARD_FLAT_COMMAND),
        (G1_FORWARD_ROUGH_ENVIRONMENT, "G1JoystickRoughTerrain", G1_FORWARD_ROUGH_COMMAND),
    ):
        forward_config = locomotion.get_default_config(forward)
        upstream_config = locomotion.get_default_config(upstream)
        assert forward_config.push_config.enable is False
        upstream_config.push_config.enable = False
        assert forward_config.to_dict() == upstream_config.to_dict()
        assert locomotion.get_domain_randomizer(forward) is locomotion.get_domain_randomizer(
            upstream
        )
        # The reusable builder is deliberately CPU-only. Override Playground's
        # GPU/Warp default for this constructor contract check; the exact Warp
        # command-through-horizon behavior is proven by the bounded H100 smoke.
        environment = locomotion.load(forward, config_overrides={"impl": "jax"})
        assert environment.sim2policy_fixed_forward is True
        assert environment.sim2policy_forward_command == command


@pytest.mark.skipif(
    importlib.util.find_spec("mujoco_playground") is None,
    reason="MJX dependencies are exercised in the pinned Nebius image",
)
def test_rough_scene_grows_the_extent_without_easing_the_terrain() -> None:
    """The enlarged field must be bigger and no gentler than upstream."""
    import numpy as np
    from mujoco_playground._src import locomotion

    register_g1_forward_environments()
    rough = locomotion.load(G1_FORWARD_ROUGH_ENVIRONMENT, config_overrides={"impl": "jax"})
    upstream = locomotion.load("G1JoystickRoughTerrain", config_overrides={"impl": "jax"})

    rough_model, upstream_model = rough.mj_model, upstream.mj_model
    assert int(rough_model.nhfield) == 1

    rough_half = float(rough_model.hfield_size[0][0])
    upstream_half = float(upstream_model.hfield_size[0][0])
    assert rough_half == pytest.approx(G1_ROUGH_HALF_EXTENT_M)
    assert upstream_half == pytest.approx(10.0)

    rough_cells = int(rough_model.hfield_nrow[0])
    upstream_cells = int(upstream_model.hfield_nrow[0])
    assert (rough_cells, int(rough_model.hfield_ncol[0])) == (G1_ROUGH_CELLS, G1_ROUGH_CELLS)
    assert rough_cells == upstream_cells * G1_ROUGH_TILE_FACTOR

    # Identical metres per cell and identical elevation amplitude: the terrain is
    # exactly as rough per step, there is simply more of it.
    assert 2 * rough_half / rough_cells == pytest.approx(2 * upstream_half / upstream_cells)
    assert float(rough_model.hfield_size[0][2]) == pytest.approx(
        float(upstream_model.hfield_size[0][2])
    )

    # The enlarged field is an exact whole-number tiling of the upstream field.
    rough_data = np.asarray(rough_model.hfield_data).reshape(rough_cells, rough_cells)
    upstream_data = np.asarray(upstream_model.hfield_data).reshape(
        upstream_cells, upstream_cells
    )
    for row in range(G1_ROUGH_TILE_FACTOR):
        for column in range(G1_ROUGH_TILE_FACTOR):
            block = rough_data[
                row * upstream_cells : (row + 1) * upstream_cells,
                column * upstream_cells : (column + 1) * upstream_cells,
            ]
            np.testing.assert_allclose(block, upstream_data, atol=1e-6)

    assert rough.sim2policy_rough_scene is True
    assert rough.sim2policy_forward_command == G1_FORWARD_ROUGH_COMMAND


@pytest.mark.skipif(
    importlib.util.find_spec("mujoco_playground") is None,
    reason="MJX dependencies are exercised in the pinned Nebius image",
)
def test_rough_scene_override_leaves_the_pinned_package_untouched() -> None:
    """The upstream identity keeps its own 20 m scene and its files on disk."""
    from mujoco_playground._src.locomotion.g1 import g1_constants

    upstream_scene = g1_constants.FEET_ONLY_ROUGH_TERRAIN_XML
    before = upstream_scene.read_bytes()
    register_g1_forward_environments()
    assert upstream_scene.read_bytes() == before
    assert 'size="10 10 .05 1.0"' in before.decode()

    from mujoco_playground._src import locomotion

    upstream = locomotion.load("G1JoystickRoughTerrain", config_overrides={"impl": "jax"})
    assert float(upstream.mj_model.hfield_size[0][0]) == pytest.approx(10.0)
    assert not getattr(upstream, "sim2policy_rough_scene", False)


@pytest.mark.skipif(
    importlib.util.find_spec("mujoco_playground") is None,
    reason="MJX dependencies are exercised in the pinned Nebius image",
)
def test_flat_environment_keeps_the_unbounded_upstream_plane() -> None:
    from mujoco_playground._src import locomotion

    register_g1_forward_environments()
    flat = locomotion.load(G1_FORWARD_FLAT_ENVIRONMENT, config_overrides={"impl": "jax"})
    assert int(flat.mj_model.nhfield) == 0
    assert not getattr(flat, "sim2policy_rough_scene", False)


def test_fixed_forward_configs_pin_command_target_and_disable_pushes() -> None:
    for name, environment, command in (
        ("g1_forward_flat_mjx.yaml", G1_FORWARD_FLAT_ENVIRONMENT, G1_FORWARD_FLAT_COMMAND),
        ("g1_forward_rough_mjx.yaml", G1_FORWARD_ROUGH_ENVIRONMENT, G1_FORWARD_ROUGH_COMMAND),
    ):
        config = load_config(ROOT / "configs" / name)
        assert config.environment == environment
        assert config.success.target_velocity == command[0]
        assert forward_command(environment) == command
        assert config.training.hyperparameters["playground_config_overrides"] == {
            "push_config.enable": False
        }
        assert config.seed == 0
