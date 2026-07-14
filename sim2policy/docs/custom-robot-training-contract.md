# Custom robot training V1 contract

Custom robot training is a three-stage product contract: an upload is structurally **validated**,
an exact robot/task/scene/runtime fingerprint is **prepared**, and only an accepted preparation can
start the fixed **custom-ppo-quick** job. Preparation verifies technical execution compatibility;
only final multi-seed evaluation reports whether the learned policy reached the task threshold.

## Supported matrix and stable reasons

V1 admits declared `biped` and `quadruped` robots, `stand-balance` and `walk-forward` tasks, and
`flat-arena` and `ramp-course` scenes. The user-selected optional object list must be empty. Ramp
Course's ramp belongs to the versioned server scene and is not an uploaded or optional object.

Saved beta setups outside that matrix remain valid drafts. They use stable reasons:
`custom-training-not-enabled`, `unsupported-robot-type`, `unsupported-task`, `unsupported-scene`,
`optional-objects-not-supported`, `not-prepared`, `preparing`, `preparation-failed`, and `ready`.

## Training-only MJCF allowlist

The existing upload validator remains the outer 1 MiB, UTF-8, primitive-only security boundary.
Preparation reparses the same XML and applies a narrower executable allowlist:

- exactly one named floating root body and free joint;
- at most the upload limits of 64 bodies, 64 joints, 64 actuators, 128 geoms, and depth 16;
- primitive `box`, `sphere`, `capsule`, `cylinder`, or `ellipsoid` robot geometry only;
- named hinge joints for every action-producing actuator;
- motor actuators only, with finite server-resolved control ranges and finite gear;
- finite compiled `qpos`, `qvel`, mass, inertia, joint range, actuator range, and model arrays;
- no uploaded floor, obstacle, camera, light, simulation override, sensor policy input, include,
  plugin, mesh, texture, height field, external reference, path, URL, or executable content.

The runtime deterministically attaches the robot subtree to a server-owned scene with gravity,
timestep, floor/ramp, contact defaults, camera/light, reset distribution, reward, termination, and
episode horizon. Unsupported content fails preparation with a bounded phase/reason and is never
executed in the SaaS API process.

## Observation, action, reward, and termination

Adapter `custom-robot-sb3-v1` orders root height and gravity-vector orientation, root linear and
angular velocity, normalized actuated-joint position/velocity pairs, previous actions, and task
target. Each action is one value in `[-1, 1]`, clipped and mapped to the corresponding verified
motor range. The ordered field list, normalization, bounds, and SHA-256 schema hashes are written to
preparation and run metadata.

Reward contract `locomotion-rewards-v1` owns all coefficients. Stand Balance rewards uprightness
and target height while penalizing root motion, action, and energy. Walk Forward adds target forward
velocity and penalizes lateral/yaw motion. Both stop on fall, non-finite state, configured runaway
position/velocity, or the fixed horizon. Seeded resets, thresholds, coefficients, and evaluation
rules are recorded in resolved configuration; users cannot edit them.

## Profiles and fingerprint

Preparation profile `custom-prepare-v1` starts at `cpu-d3/4vcpu-16gb`, a 50 GiB disk, and a
10-minute hard timeout. It verifies manifests/digests, compilation, finite spaces/dynamics, three
seeded reset and zero/random rollouts, headless rendering, the Gymnasium/SB3 checker, and a 2,048
step PPO save/reload/inference cycle.

Training profile `custom-ppo-quick-v1` starts at `cpu-d3/8vcpu-32gb`, a 100 GiB disk, a one-hour
timeout, eight vector environments, and 100,000 PPO timesteps with fixed hyperparameters,
checkpoints, and a 20-episode/five-seed final evaluation. These are provisional server-owned values;
production enablement must benchmark all eight canonical combinations and freeze the smallest
dependable shapes without adding user controls.

The accepted preparation fingerprint is canonical JSON over schema version, robot digest, setup
digest, immutable runtime image, adapter version, reward version, and preparation-profile version.
Changing any material input requires preparation again; historical jobs retain their original
fingerprint and immutable input snapshot.

Versioned JSON Schemas live under `sim2policy/schemas/custom_robot/`, with golden documents under
`sim2policy/tests/fixtures/custom_robot/`. The runtime builds one immutable SB3 image for every
robot; MJCF and normalized setup JSON are bounded S3 runtime input, never Docker build context.
