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

Reward contract `locomotion-rewards-v20` owns all coefficients. Stand Balance rewards uprightness
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
height by nature. Measured fraction of target reached at the shipped targets is 0.93–1.01 (biped)
and 0.92–0.94 (quadruped) against a 0.50 crawl.

That posture floor is a height, and v17 exists because a height cannot describe a posture on its
own. Both locomotion tasks now also bound **what is holding the robot up**: the fraction of the
episode spent touching the ground with anything that is not a foot must stay at or below
`success_max_unsupported_contact` (0.25), and the same signal is priced in the reward at
`ground_contact` −1.0. "Foot" is measured rather than declared — `CustomRobotEnv` settles the model
from its authored pose under zero control once at construction and records whatever it comes to rest
on, which resolves to the quadruped's four shin tips and the biped's two foot boxes. Anything else
reaching the ground later is the robot resting on a part of itself that is not a foot. Contact is
counted against every world-owned geom, not just the arena floor, so it means the same thing on a
ramp or a step; `recover-from-fall` is exempt, because it resets the robot onto its side and
non-foot contact there is the task rather than a failure.

The rate is deliberately not a prohibition, and it is measured over the episode rather than sampled
at the end. A stride may brush a shin without being carried by it, and the *instantaneous* contact
set of a kneeling quadruped at the final step is sometimes nothing but feet. The bound also cannot
fire on a working biped — swept across 1,713 joint configurations with the pelvis at or above 0.70 m,
the closest any non-foot geom comes to the floor is +1.5 cm (the shin cap, which sits directly above
the foot box).

**The bound is 0.25, and the first value tried — 0.1 — was set by reasoning rather than measured.**
It came from the assumption that a working gait reads near zero. A measured quadruped gait reads
0.105–0.119: twenty episodes of full-horizon walking at 0.820–0.841 m/s against a commanded 0.8,
zero falls, torso level at 0.961–1.000, scored 0/20 by a bound a percentage point and a half too
low. A quadruped brushes a thigh as it swings the leg through; that is a stride, not a crawl. The
behaviours are five times apart, so the bound does not need precision, only to sit in the gap:

| behaviour | unsupported contact rate |
| --- | --- |
| kneeling, driven to full knee flexion | 0.55–0.64 |
| walking, 0.83 m/s, zero falls | 0.105–0.119 |
| standing on its feet | 0.000–0.007 |
| biped, either task | 0.000–0.042 |

0.25 clears the gait by more than 2× and rejects the kneel by more than 2×. It was raised only
after watching the render — loosening a threshold because a policy failed it is precisely how the
kneeling got certified for eight versions, and the only thing separating a correction from a
repeat of that mistake is looking at the rollout first.

### Where the feet are

Height and ground contact are two of the three things "standing on its legs" turned out to mean,
and they do not imply the third. v20 exists because the quadruped came off its knees and went
straight into a **splits** — front legs folded forward, rear legs raked back, every foot on the
ground and the torso level at exactly the height asked for. Both earlier signals pass that pose.
Height says how high the body is; ground contact says the feet are what carry it; neither says the
feet are *underneath the robot*.

`stance_offset` is the horizontal distance from each foot to the joint that carries its limb — the
joint where the leg meets the body, found by walking the kinematic tree up from the foot — stated as
a fraction of that limb's reach and averaged over the feet. 0 is a foot directly below its hip; 1 is
a leg stuck straight out. Like "foot", the hip is derived from the model rather than named, so it
needs no per-morphology table. Measured on constructed poses:

| pose | stance offset |
| --- | --- |
| quadruped, feet under hips, any height 0.36–0.59 m | 0.00–0.27 |
| quadruped, trot with a diagonal pair swung 20° | 0.29 |
| biped, standing, any crouch depth | 0.04–0.09 |
| biped, mid-stride, legs split 25° / 45° | 0.42 / 0.71 |
| **quadruped, the splits it had settled into** | **0.82** |

The widest *good* number in that table belongs to a walking biped, not to any stance, so the reward
charges only what exceeds `stance_tolerance` (0.35) rather than charging from zero — a robot reaches
its widest split every step, and billing that would bill it for walking. Priced at `stance` −2.0,
which makes the splits cost (0.82 − 0.35) × 2.0 ≈ 0.94/step against the kneel's 1.00: the two
posture faults are the same mistake wearing different geometry, and the policy should not be able to
trade one for the other. Success bounds the **episode mean** at `success_max_stance_offset`, not the
final step, because a stride passes through its widest split every cycle.

**The height target is not the cause, and this was checked before the term was written.** The sample
quadruped can put a foot directly under every hip at any body height between 0.36 and 0.57 m, so no
target in the usable range forces a splay. Nothing had ever asked it to, and for a robot whose eight
joints all pitch, a splits is the *more* stable answer — so that is what PPO found. Heights were
held unchanged across v20 for that reason, so the attribution stayed clean.

**Measured, v20, all four defaults at one version.** The splits is gone everywhere and the bound was
never the binding constraint:

| cell | success | stance offset | unsupported | height | notes |
| --- | --- | --- | --- | --- | --- |
| quad stand | 20/20 | 0.256–0.277 | 0.000–0.016 | 0.362–0.365 | upright 0.993–0.994, zero falls |
| quad walk | 20/20 | 0.252–0.257 | 0.005–0.020 | 0.297–0.340 | 0.82–0.84 m/s, zero falls |
| biped stand | 19/20 | 0.166–0.283 | 0.000 | 0.696 ×19 | one seed tips at 0.302 |
| biped walk | 18/20 | 0.332–0.354 | 0.000–0.058 | up to 0.913 | 0.39–0.63 m/s |

That fixes the 0.5 bound as measured rather than assumed: the widest good episode is the biped's
gait at 0.354, and the splits holds 0.82, so the bound sits with 41% clearance below and 39% above.
The 0.35 deadband is confirmed by the same row — a walking biped averages 0.332–0.354, i.e. right at
the free-zone edge, so it is charged almost nothing for walking, which is what the deadband is for.

### The crouch is the morphology, not the target — a refuted hypothesis

The v20 quadruped stands rock-steady at 0.365 m, which for legs of 2 × 0.28 m puts its hips at 53.2°
against a 55° stop: **1.8° of travel left**. Two independent measurements agree it is there — the
height implies that pose, and the measured stance of 0.266 matches the 0.268 the pose predicts.

That looked like a defect worth fixing. A robot at its joint stop has nothing left to correct a
disturbance with, and it reads to a person as a robot crouched as low as it will go. So v21 raised
the targets to move it to mid-range:

| target scale | body height | hip | knee | hip headroom |
| --- | --- | --- | --- | --- |
| 0.62 (stand, shipped) | 0.365 | 53.2° | −106.5° | 1.8° |
| 0.75 (v21 walk) | 0.442 | 42.7° | −85.4° | 12.3° |
| 0.80 (v21 stand) | 0.471 | 38.0° | −76.1° | 17.0° |

**Measured, and it does not work.** The robot does not track the taller target at all — it stayed at
the same ~0.36 m and spent the mismatch on tilting instead:

| cell | v20 (0.62/0.55) | v21 (0.80/0.75) |
| --- | --- | --- |
| quad stand | **20/20**, h 0.362–0.365, stance 0.256–0.277, unsupported ≤0.016 | 19/20, h 0.283–0.386, stance 0.316–0.351, unsupported ≤0.118 |
| quad walk | **20/20**, h 0.297–0.340, 0.82–0.84 m/s | **15/20 — below the gate**, h 0.284–0.480 |

Raising the ask by 29% moved the achieved height by roughly nothing, degraded the stance, started
scuffing the knees, and pushed walk-forward under threshold. The render shows why: v21 stands
nose-down and asymmetric rather than taller. **The deep crouch is what this morphology settles at,
not an artefact of the target**, and it is consistent with the same pitch-only limitation behind
`recover-from-fall` — near-straight legs are exactly where differential leg extension has least roll
authority, so standing tall is the *less* stable option for this robot.

v21 is therefore reverted and the shipped values are v20's. This is recorded rather than deleted
because the joint-stop reasoning is sound and will look attractive again; it has been tested, and
the robot's answer is no.

One thing the geometry does say independently: v20's *walk* target of 0.55 asks for 0.324 m, which is
below the 0.351 m floor of the entire feet-under-hips envelope, so no pose with the feet under the
hips can reach it. The measured walk stance of 0.252–0.257 is the robot getting as close as the
envelope allows, and it passes 20/20 — but that target has no headroom underneath it either.

**Raising a height target is only safe once stance is scored.** v17 asked 0.85 with no stance term
and the robot spent the extra height on a splits instead of on standing taller: 9/20 on walk with 45%
falls. Height says how far to extend; only the stance bound says where to put the feet.

Walk Forward's `height` weight is 1.5, and it was bracketed rather than guessed. At 0.6 the upright
gait was worth only ~13% more total reward than a crouch, and a measured Nebius run scored 0.000 at
all twelve checkpoints while reward climbed 178 → 3493 — it never took the trade. At 2.0 the biped
stood at 0.867 and stopped dead, velocity 0.01, failing the velocity bound instead of the posture
floor. 1.5 gives 20/20 at heights 0.782–0.851 and velocity 0.83, with the training curve reaching
1.00 at 1.5M and holding it to 3M.

That trap is biped-specific and the quadruped shows why: it walks at 0.314 and stands at 0.314, so
no height weight can pay it to stop, and it scored 0.95+ at 1.2, 1.5 and 2.0 alike. The biped walks
at ~0.72 but stands at ~0.87, so every increase in the weight raises the payoff for freezing. Note
the reward still *prefers* walking at 2.0 — a stationary robot loses about 1.8/step on the velocity
Gaussian against ~0.5/step gained on height — so that failure is PPO converging to the easier
behaviour first, not the reward ranking them wrongly. Raising the weight cannot fix it.

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
pose and a trained policy keeps 85–90% of it. The quadruped spawns with its legs extended beneath it
and v16 asked it for 57.5% of that — a number this document defended as "normal for the shape rather
than a crouch", and which was neither. Its legs reach 0.59 m and its knees hang 0.28 m below the
torso, so 0.339 m is six centimetres above its own knee joints: at that height standing and kneeling
are the same measurement, and the shipped policy met the target to within a centimetre by folding
its legs and lying on its shins. Nothing in the contract disagreed, because height was the only
thing describing posture and height was exactly what it had been told to produce. It took watching
the render to see it. A single scale was measured both ways at the production profile and each
choice broke one robot; the shipped rows below are published-checkpoint scores over twenty distinct
seeds, and the rejected rows are noted where they came from a different harness.

| robot | scale | asks for | stand | walk | posture |
| --- | --- | --- | --- | --- | --- |
| quadruped | 0.575 | 0.339 | 20/20, h 0.314 | 20/20, h 0.313–0.319 | **kneeling — shins on the floor** |
| quadruped | 0.900 | 0.530 | 0/20, h 0.256 | 0.95, h 0.264 | crawling at 45% of reference |
| quadruped | 0.850 | 0.501 | 17/20, h 0.286–0.394 | 9/20, 45% falls | **on its feet**, but reaching |
| **quadruped** | **0.620 / 0.550** | 0.365 / 0.324 | **20/20**, h 0.349–0.359 | 0/20 at bound 0.10 † | on its feet, bounding gait |

† Every walk episode ran the full horizon at 0.820–0.841 m/s with zero falls and read 0.105–0.119
against a bound of 0.10 — see the contact-rate table above for why that bound was wrong. The
re-measurement at 0.25 is pending; it is not simply the same policy re-scored, because the progress
evaluation's success signal also changes and with it which checkpoint gets published.
| biped | 0.575 | 0.537 | 0.95, h 0.523 | 20/20, h 0.539 | crossed the arena on one knee |
| biped | 0.800 | 0.747 | 20/20, h 0.694 | not measured | squat: knees folded, torso pitched back |
| **biped** | **0.850** | 0.794 | **20/20**, h 0.776–0.786 | **18/20**, h 0.300–0.902 | upright torso, extended stride |
| biped | 0.900 | 0.840 | 17/20, h 0.741–0.798 | 20/20 | upright, but three falls at steps 108–185 |

Both 0.575 rows are the same failure wearing different numbers: 0.34 m is a kneel for the quadruped
and 0.54 m is one knee down for the biped, and both scored 20/20 on walk. The scores in this table
are worth exactly what the posture column is worth — which is why v17 measures posture directly
rather than inferring it from the score.

**The quadruped's 0.85 row is the one to read carefully, because it separates the two changes.** The
posture fix worked: eighteen of twenty stand-balance episodes spent under 0.3% of their steps
touching the ground with anything but a foot, against the 0.55–0.64 a kneeling robot reads, and the
render shows the body carried on the four leg tips. The height ask did not: the robot held
0.286–0.394 against 0.501, one episode was rejected purely for standing at 0.360, and the walk cell
fell in nine of twenty trying to carry a gait that tall. So the target came down to what the robot
demonstrably holds — 0.62 standing, 0.55 walking, the latter lower because this robot walks in a
crouch.

That lands the quadruped's target back near v16's 0.575, and it is worth being explicit about why
that is not a circle. **v16 stood at 0.314 on its knees; v18 stands at ~0.35 on its feet.** The
height barely moved because the height was never what was wrong — a quadruped kneels at very nearly
the height it stands at, and the two are separated only by what is carrying it.

The quadruped-at-0.9 stand row scored 0.0 at *every* checkpoint from 500k to 3M under the v13
reward. The 0.85 row settles what that meant: with a ground-contact cost and success-first
checkpoint ranking in place, the same robot reaches 17/20 at a nearly-as-high target, so the earlier
collapse was losing to a cheaper local optimum rather than hitting a physical ceiling. Actuator
torque is not the ceiling either — holding the tall stance needs 15.7 N·m of the 45 N·m available,
*less* than the 25.2 N·m the crouch needs. What the robot runs out of is balance authority: all
eight of its joints are pitch-only, so it cannot correct roll except through differential leg
extension, which is weakest when the legs are straight.

The biped's 0.85 is the interesting row, and the rule it illustrates is *ask for a height the robot
can actually hold*. At 0.90 the policy strains for 0.840 and only ever reaches 0.741–0.798, and the
three episodes it loses are falls rather than posture failures — standing on near-straight legs is
an inverted pendulum with little recovery authority. At 0.85 the ask sits inside the band the robot
already holds, the height term stops competing with balance, and it holds 0.776–0.786 across all
twenty episodes — a 1 cm spread, taller on average than the 0.90 policy, with no falls. Dropping
further to 0.80 also scores 20/20 and buys it with a squat, which is what the posture requirement
exists to reject.

The quadruped got *worse* when asked for more, and the standing account of that was the height
term's Gaussian: its width is `target * 0.25`, so at a target the robot cannot reach the term goes
flat and nothing opposes trading height away. The gradient does weaken — at the kneeling height the
term pulls 6.4/m towards a 0.339 target and 1.7/m towards a 0.530 one — but flatness is only half of
it, and the smaller half. The other half is that kneeling was a *good* place to sit: it collects
`alive` and `upright` almost in full, it is far more stable than balancing on four point feet with
no roll actuation, and until v17 nothing charged for it. A shaping term cannot out-bid a local
optimum that is both cheaper and safer, which is the same lesson the walk-forward height weight
taught at 2.0. `ground_contact` removes the optimum rather than trying to outweigh it.

`target_height_scale(task, robot_type)` resolves the per-type table, and raises for a robot type
the task accepts but has no measured target for. **When setting one, check it against the robot's
own geometry before the score:** the sample quadruped's legs reach 0.59 m and its knees sit 0.28 m
down, so anything below about 0.40 m is a target only a kneeling robot can hit, and no success rate
computed against it means what it appears to mean.

## Profiles and fingerprint

Preparation profile `custom-prepare-v1` starts at `cpu-d3/4vcpu-16gb`, a 50 GiB disk, and a
10-minute hard timeout. It verifies manifests/digests, compilation, finite spaces/dynamics, three
seeded reset and zero/random rollouts, headless rendering, the Gymnasium/SB3 checker, and a 2,048
step PPO save/reload/inference cycle.

Training profile `custom-ppo-quick-v3` starts at `cpu-d3/16vcpu-64gb`, a 100 GiB disk, a
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
