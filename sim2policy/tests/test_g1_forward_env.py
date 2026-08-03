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
        environment = locomotion.load(forward)
        assert environment.sim2policy_fixed_forward is True
        assert environment.sim2policy_forward_command == command


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
