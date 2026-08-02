"""Playground PPO entry point with Sim2Policy-owned environment registration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sim2policy.g1_forward_env import (
    register_g1_forward_environments,
    upstream_environment,
)


def main(argv: Sequence[str] | None = None) -> Any:
    register_g1_forward_environments()

    from absl import app
    from learning import train_jax_ppo  # type: ignore[import-untyped]

    original_get_rl_config = train_jax_ppo.get_rl_config

    def get_rl_config(environment: str) -> Any:
        # Playground 0.2.0 hard-codes PPO defaults by upstream identity. Mapping
        # only the lookup preserves the exact G1 PPO contract for our adapter.
        return original_get_rl_config(upstream_environment(environment))

    train_jax_ppo.get_rl_config = get_rl_config
    return app.run(train_jax_ppo.main, argv=list(argv) if argv is not None else None)


if __name__ == "__main__":
    main()
