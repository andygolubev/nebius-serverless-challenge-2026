"""Linux-container smoke for every supported custom-robot runtime combination."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from sim2policy.custom_robot_env import CustomRobotEnv


def main() -> None:
    samples = Path("/samples")
    if not samples.is_dir():
        samples = Path(__file__).resolve().parents[2] / "saas" / "samples" / "robots"
    combinations = 0
    for filename in ("sample-biped.xml", "sample-quadruped.xml"):
        robot_xml = (samples / filename).read_text(encoding="utf-8")
        robot_type = "biped" if "biped" in filename else "quadruped"
        for task in ("stand-balance", "walk-forward"):
            for scene in ("flat-arena", "ramp-course"):
                env = CustomRobotEnv(
                    robot_xml,
                    {
                        "schema_version": 1,
                        "robot_type": robot_type,
                        "task_template_id": task,
                        "scene_preset_id": scene,
                        "objects": [],
                    },
                )
                try:
                    observation, _ = env.reset(seed=19)
                    observation, reward, _, _, _ = env.step(
                        np.zeros(env.model.nu, dtype=np.float32)
                    )
                    assert env.observation_space.contains(observation)
                    assert np.isfinite(reward)
                    combinations += 1
                finally:
                    env.close()
    assert combinations == 8
    print("custom robot container matrix: 8/8")


if __name__ == "__main__":
    main()
