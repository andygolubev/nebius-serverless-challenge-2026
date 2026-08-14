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

Reward contract `locomotion-rewards-v12` owns all coefficients. Stand Balance rewards uprightness
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

Walk Forward also requires a posture: the body must be at or above `success_min_height_of_target`
(0.8) of the height the task's reward asked for. Until v12 the criterion was survive + velocity +
drift and nothing else, so a policy that crossed the arena folded onto one knee at 58% of its
standing height scored 20/20 and was reported as a clean gait — the termination floor sits far below
a crouch, and Stand Balance was the only task that ever checked height. The bar is a fraction of the
*target* rather than of `reference_height` so that it needs no per-morphology table of its own: 0.8
of reference would pass the biped and fail the quadruped outright, which walks at 0.54 of its spawn
height by nature. Measured fraction of target reached at the shipped targets is 0.97 (biped) and
0.88 (quadruped) against a 0.50 crawl.

`task_threshold_achieved` is `success_rate >= 0.9`, and the bar travels with the metrics as
`task_success_rate_threshold`. It was every episode until v11, which is not a sound rule for a
twenty-seed sample of a stochastic rollout: at a per-episode success rate of 0.95 an all-or-nothing
gate reports failure about two runs in three, and even a policy losing one episode in a hundred is
marked failing 18% of the time. Two runs of the same revision measured that directly — a quadruped
scoring 20/20 and passing, a biped scoring 19/20 and being reported below threshold on the strength
of one initial pose. The measured `success_rate` is always reported next to the boolean.

Those twenty episodes must be twenty *distinct* initial conditions, which they were not before v12.
The seed rule was `base[index % len(base)] + index`, which collides whenever two base seeds differ
by a multiple of the number of base seeds; at the shipped profile base 37 at index 2 and base 23 at
index 16 both produce seed 39. The gate therefore sampled nineteen conditions and counted one twice
— and in a measured biped run that duplicated seed was the failing one, scoring the policy 0.90
instead of the 18/19 it earned. `evaluation_seeds()` now spaces the families by a stride larger than
any base seed, and rejects duplicate or oversized base seeds rather than silently colliding.

**Recover From Fall cannot currently be completed by the sample quadruped**, and this is a property
of the robot rather than of the thresholds. The reset rolls the body 1.2–1.45 rad about world X,
while all eight of that model's actuators are `axis="0 1 0"` — pitch only. A body-Y torque has a
world-X component of exactly zero at every roll angle, so there is no actuator authority about the
axis the robot must rotate, and at 69–83° of roll the leg swing plane is 0.93–0.99 vertical, so
swinging the legs yaws the body instead of righting it. Measured runs score 0.000 at every
checkpoint through the full budget and never reach even `minimum_upright`. Its height scales are
separately mis-set — `target_height_scale` 0.9 asks for 0.495 against a measured standing posture of
0.313–0.321 — but correcting them does not make the task learnable and is not the fix. Tipping about
pitch rather than roll is the change a pitch-only quadruped could act on.

Every height threshold — the reward target, the fall line, and the success band — is a multiple of
`reference_height`, which is sampled once per reset at the end of a short zero-control settle. The
settle exists because the authored spawn height is not the height the model rests at, and deriving
the fall line from the spawn height terminated episodes during the drop. v10 shortened it from 20
control steps to 5. Contact is reached in about five; every step beyond that is a robot standing
under no torque, so for anything that does not balance passively the settle stops measuring a
resting pose and starts sampling a fall. Because the sample scales every threshold, that made the
success band a per-episode random variable — measured spread across the twenty evaluation seeds was
0.2908 m (quadruped) and 0.3503 m (biped) at 20 steps against 0.0009 m at 5 — and it left the
low-sample episodes starting from a stationary but half-collapsed pose, since `qvel` is zeroed
afterwards. A five-step settle reports the resting pose for both shipped robot types.

That resting pose is not the same *kind* of pose for both, which is why `target_height_scale` is
stated per robot type for the two locomotion tasks. The biped's spawn pose is already a standing
pose and a trained policy keeps 88% of it; the quadruped spawns with its legs extended beneath it
and walks bent-legged at ~54%, which is normal for the shape rather than a crouch. A single scale
was measured both ways at the production profile and each choice broke one robot. The shipped
rows are the published-checkpoint scores over twenty distinct seeds; the rejected rows are noted
where they came from a different harness.

| robot | scale | asks for | stand | walk | posture |
| --- | --- | --- | --- | --- | --- |
| **quadruped** | **0.575** | 0.339 | **20/20**, h 0.314 | **20/20**, h 0.298 | bent-leg stance and stride |
| quadruped | 0.900 | 0.530 | 0/20, h 0.256 | 0.95 final-policy, h 0.264 | crawling at 45% of reference |
| biped | 0.575 | 0.537 | 0.95 in production, h 0.523 | 20/20, h 0.539 | crossed the arena on one knee |
| **biped** | **0.900** | 0.840 | **18/20**, h 0.807–0.840 | **20/20**, h 0.811 | upright torso, extended stride |
| biped | 0.800 | 0.747 | 20/20, h 0.694 | not measured | squat: knees folded, torso pitched back |

The quadruped-at-0.9 stand row scored 0.0 at *every* checkpoint from 500k to 3M, so best-checkpoint
selection cannot rescue it. The biped-at-0.8 row is the reason the biped's 18/20 is left alone: the
extra two episodes are bought with a crouch.

The quadruped gets *worse* when asked for more, because the height term is a Gaussian of width
`target * 0.25`: at a target the robot cannot reach the term is flat, so nothing opposes trading
height for velocity and the policy settles into a crawl. An unreachable target therefore reads as
no gradient rather than as a hard task, which is the failure mode the per-type table exists to
prevent. `target_height_scale(task, robot_type)` resolves it, and raises for a robot type the task
accepts but has no measured target for.

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
