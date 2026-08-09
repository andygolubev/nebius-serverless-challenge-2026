# Custom robot training V2 contract

Custom robot training is a three-stage product contract: an upload is structurally **validated**,
an exact robot/task/scene/runtime fingerprint is **prepared**, and only an accepted preparation can
start the fixed **custom-ppo-quick** job. Preparation verifies technical execution compatibility;
only final multi-seed evaluation reports whether the learned policy reached the task threshold.

## Supported matrix and stable reasons

V2 admits declared `biped` and `quadruped` robots, every task compatible with the declared family,
all four server scenes, and up to six total normalized preset/custom primitives. Quadrupeds support
`stand-balance`, `walk-forward`, and `recover-from-fall`; bipeds support the first two. Flat, Ramp,
Hurdle, and Step scenes plus bounded Box, Ramp, Hurdle, and Step objects all use the same fixed
runtime. Preset objects are included in the six-object total and are carried in the exact normalized
setup input.

Every catalog-valid saved setup uses lifecycle reasons `custom-training-not-enabled`,
`not-prepared`, `preparing`, `preparation-failed`, and `ready`. Unsupported task/scene/object reasons
remain bounded defensive categories for corrupt or historical data; the builder cannot persist such
a payload.

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
timestep, floor and normalized primitive geometry, contact defaults, camera/light, reset
distribution, reward, termination, and episode horizon. Unsupported content fails preparation with
a bounded phase/reason and is never
executed in the SaaS API process.

## Observation, action, reward, and termination

Adapter `custom-robot-sb3-v2` orders root height and gravity-vector orientation, root linear and
angular velocity, signed lateral offset from the start line and heading as a cos/sin pair,
normalized actuated-joint position/velocity pairs, previous actions, and task target. The offset and
heading fields are new in v2: the gravity vector is invariant to yaw and the velocities are in the
root frame, so a v1 policy could not observe heading error or accumulated sideways displacement —
the very quantity `walk-forward` success bounds. Each action is one value in `[-1, 1]`, clipped and mapped to the corresponding verified
motor range. The ordered field list, normalization, bounds, and SHA-256 schema hashes are written to
preparation and run metadata.

Reward contract `locomotion-rewards-v9` owns all coefficients. Stand Balance rewards uprightness
and target height while penalizing root motion, action, and energy. Walk Forward adds target forward
velocity and target walking height, and penalizes lateral/yaw motion; it is scored as a success when
the robot survives the full horizon with an episode-mean forward velocity at or above
`success_min_velocity` and lateral drift within bounds, rather than on the root velocity sampled at
the final step. Recover From Fall starts a quadruped from a bounded
side-fallen free-root pose and rewards upright/height recovery while bounding motion, action, and
energy. Falling terminates balance/walk episodes but not recovery episodes; non-finite state,
configured runaway position/velocity, and the fixed horizon remain universal bounds. Seeded resets,
thresholds, coefficients, and evaluation rules are recorded in resolved configuration; users cannot
edit them.

## Profiles and fingerprint

Preparation profile `custom-prepare-v1` starts at `cpu-d3/4vcpu-16gb`, a 50 GiB disk, and a
10-minute hard timeout. It verifies manifests/digests, compilation, finite spaces/dynamics, three
seeded reset and zero/random rollouts, headless rendering, the Gymnasium/SB3 checker, and a 2,048
step PPO save/reload/inference cycle.

Training profile `custom-ppo-quick-v2` starts at `cpu-d3/16vcpu-64gb`, a 100 GiB disk, a
three-hour timeout, sixteen subprocess vector environments, and 3,000,000 PPO timesteps with
fixed hyperparameters, running observation/reward normalisation, periodic checkpoints, and a
20-episode/five-seed final evaluation. The policy published as final is the best-scoring
checkpoint across those evaluations, not simply the last one. These are provisional server-owned values;
production validation expands from the eight historical V1 anchors to representative coverage of
every new task, terrain, and object family before freezing dependable shapes without adding user
controls.

The accepted preparation fingerprint is canonical JSON over schema version, robot digest, setup
digest, immutable runtime image, adapter version, reward version, and preparation-profile version.
Changing any material input requires preparation again; historical jobs retain their original
fingerprint and immutable input snapshot.

Versioned JSON Schemas live under `sim2policy/schemas/custom_robot/`, with golden documents under
`sim2policy/tests/fixtures/custom_robot/`. The runtime builds one immutable SB3 image for every
robot; MJCF and normalized setup JSON are bounded S3 runtime input, never Docker build context.
