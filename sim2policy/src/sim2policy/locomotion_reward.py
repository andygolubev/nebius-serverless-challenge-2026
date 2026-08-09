"""The one reward scale a locomotion run may tune, and the trap it can fall into.

Pinned Playground G1 pays nothing for staying upright (``alive = 0.0``) and
applies a one-off ``termination = -100.0`` under a 0.97 discount at 50 Hz --
an effective lookahead of 0.67 s.  A fall five seconds away is discounted to
5e-4, so the critic cannot predict it and the penalty arrives as noise.  The
measured consequence is a policy that survives only ~80% of episodes, against
gates that wanted every episode perfect.

Turning ``alive`` on gives survival a dense, learnable signal.  The danger is
the opposite failure: pay enough for merely existing and standing still becomes
a cheaper policy than the task.  This repository has already measured that --
``custom_robot_contract.py`` halved its alive weight from 1.0 to 0.5 in v9
because "standing still collected alive + upright + height ~= 2.6 per step for
free while walking added at most 1.4 on top".

G1's own ``_cost_stand_still`` does not protect against this: it multiplies by
``cmd_norm < 0.01``, so under a 0.8-1.0 m/s forward command it is identically
zero.  The only thing holding the robot to the task is the velocity-tracking
reward, so the ratio between what walking pays and what standing pays is the
number that decides whether a survival reward is safe.

This module stays free of MuJoCo and MJX imports so the SB3-only install keeps
working; the constants are the reviewed values of pinned Playground 0.2.0 and
are asserted against the real environment in the MJX test suite.
"""

from __future__ import annotations

import math

# Pinned Playground 0.2.0 G1 joystick reward configuration.
TRACKING_SIGMA = 0.25
TRACKING_LIN_VEL_SCALE = 1.0
# The upstream default this change turns on, and the value T1 -- the other
# humanoid in the same pinned package -- ships with.
UPSTREAM_ALIVE_SCALE = 0.0
T1_ALIVE_SCALE = 0.25
# Walking must out-pay standing by at least this much, so surviving can never
# become a cheaper policy than the declared task.
MIN_WALK_TO_STAND_RATIO = 3.0


class SurvivalRewardError(ValueError):
    """Raised when a survival reward would outcompete the locomotion task."""


def tracking_reward(target_velocity: float, actual_velocity: float) -> float:
    """Pinned ``_reward_tracking_lin_vel``: ``exp(-|cmd - v|^2 / sigma)``."""
    error = (float(target_velocity) - float(actual_velocity)) ** 2
    return TRACKING_LIN_VEL_SCALE * math.exp(-error / TRACKING_SIGMA)


def walk_vs_stand_ratio(alive: float, target_velocity: float) -> float:
    """Per-step return for tracking the command, over that for standing still.

    Both sides omit ``feet_air_time`` (2.0) and ``feet_phase`` (1.0), which pay
    only when the robot is actually stepping.  Leaving them out understates
    walking's advantage, so the ratio is a conservative bound.
    """
    walking = float(alive) + tracking_reward(target_velocity, target_velocity)
    standing = float(alive) + tracking_reward(target_velocity, 0.0)
    if standing <= 0.0:
        return math.inf
    return walking / standing


def check_survival_reward(alive: float, *, target_velocity: float) -> None:
    """Reject a survival reward that would make standing still competitive."""
    if not isinstance(alive, (int, float)) or isinstance(alive, bool):
        raise SurvivalRewardError("MJX reward_config.scales.alive must be a number")
    if math.isnan(alive) or alive < 0.0:
        raise SurvivalRewardError(
            "MJX reward_config.scales.alive must be a non-negative number"
        )
    ratio = walk_vs_stand_ratio(alive, target_velocity)
    if ratio < MIN_WALK_TO_STAND_RATIO:
        raise SurvivalRewardError(
            f"reward_config.scales.alive {alive:g} leaves walking only {ratio:.2f}x "
            f"better than standing still at {target_velocity:g} m/s, below the "
            f"required {MIN_WALK_TO_STAND_RATIO:g}x margin. A survival reward this "
            "large makes standing still a cheap local optimum."
        )
