## Why

The G1 rough-terrain acceptance gate cannot be satisfied by any policy. The pinned Playground rough
scene is a **finite 20 m × 20 m height field with no floor outside it**
(`<hfield size="10 10 .05 1.0"/>`, and that hfield geom is the only thing in the worldbody). The
robot spawns dead centre — `reset()` randomizes yaw, joints and velocities but never `qpos[0:2]` —
so the distance to the edge along any heading is 10 m (axis-aligned) to 14.14 m (diagonal). The gate
asks for 1,000 steps × 0.02 s = **20 s** of walking at a commanded 0.8 m/s, which is **16 m of
travel**. The robot runs out of world before it runs out of horizon.

| commanded | travel needed in 20 s | max available | yaws that fit |
| --- | --: | --: | --: |
| 1.0 m/s (`g1_mjx.yaml`, the published run) | 20.0 m | 14.14 m | **0%** |
| 0.8 m/s (`g1_forward_rough_mjx.yaml`, current authorization) | 16.0 m | 14.14 m | **0%** |
| 0.6 m/s (preferred-gate mean) | 12.0 m | 14.14 m | 25% |
| 0.4 m/s (hard-gate minimum) | 8.0 m | 14.14 m | 100% |

The published run `showcase-gallery-g1-20260801-16-g1-s0-rough` confirms it: 20/20 episodes
terminated, lengths 610–934, **none reached 1,000**, and per-episode path length
(`mean_velocity × length × 0.02`) has a hard floor at **10.47 m** against a geometric floor of 10.0 m.
Its `ranking_explanation` covers 14 candidate checkpoints and shows `no_fall_count` — the first
ranking key — stuck at **1.0 at both 23.1M and 46.2M steps**, with the 46.2M checkpoint selected out
of 348.6M trained. Over that range `mean_velocity` rose 0.75 → 0.96 and `mean_reward` 19.3 → 21.9.
Training worked; it bought speed, which makes the geometry problem strictly worse. No training
budget can fix this.

The edge also corrupts the training signal, not just the measurement. The policy observation carries
linear velocity, gyro, gravity, command, joint state, last action and gait phase; the privileged
critic observation adds only `root_height`. **Neither carries global position.** The critic
therefore cannot learn where the cliff is, so the `termination = -100.0` penalty that every episode
collects at the edge arrives at an unpredictable time and is irreducible noise in the advantage
estimates. Removing the edge should improve the policy, not merely make it measurable.

`openspec/README.md` says that when code and spec disagree, one of them is a bug. Here the **spec is
the bug**: `showcase-run-curation`'s "Reviewed fixed-forward H100 G1 recovery" requires
`[0.8, 0.0, 0.0]` held "for the full 1,000-step episode" *and* "20/20 1,000-step episodes without any
environment termination" on a scene where those two clauses are mutually exclusive.

## What Changes

- Add a **server-owned rough-terrain scene** for `G1ForwardRoughTerrain` with the height field
  enlarged from 20 m × 20 m to **60 m × 60 m** (half-extent 30 m), built by tiling the shipped
  `hfield.png` 3 × 3 at **identical spatial resolution (7.812 cm/cell) and identical elevation
  amplitude (0.05 m)**. Per-step terrain difficulty is unchanged by construction; only the extent
  grows.
- Register the enlarged scene through the existing reviewed-override pattern in
  `g1_forward_env.py`, which already subclasses upstream and preserves the upstream randomizer. The
  pinned `mujoco-playground==0.2.0` package is **not** modified.
- Add a **feasibility invariant** to config validation: a locomotion run whose
  `target_velocity × horizon × ctrl_dt` exceeds the scene's worst-case spawn-to-edge distance SHALL
  fail before any paid GPU step, rather than producing an unreachable gate.
- **BREAKING** for campaign authorization: `user_reviewed_rough_08_full_v2` is bound to the old
  20 m scene and its matrix digest. A new authorization mode and campaign ID are required; the
  existing exhausted authorization is not reused or extended.
- The published G1 card is **not** re-pinned by this change. It stays an honest verified recording
  until a campaign produces accepted evidence. Whether to spend a new campaign job is a separate
  operator decision that this change only unblocks.

Explicitly **not** changed: rewards, PPO hyperparameters, physics, `ctrl_dt`/`sim_dt`, reset and
noise, observation and action spaces, the termination predicate, pushes (stay disabled), the flat
scene (its floor is an infinite `type="plane"`, so it was never affected), and the acceptance
thresholds themselves.

## Capabilities

### New Capabilities
- `locomotion-scene-extent`: server-owned locomotion scene geometry, and the invariant that a
  configured command and horizon must physically fit within the scene from the spawn point along any
  yaw — validated before submission rather than discovered after a paid run.

### Modified Capabilities
- `policy-training-backends`: the MJX path gains a reviewed server-owned scene override for
  `G1ForwardRoughTerrain`, alongside the existing fixed-forward command override, without editing
  the pinned Playground package.
- `showcase-run-curation`: the G1 recovery requirement must state the scene extent its gate depends
  on, and must carry a new authorization mode rather than silently reusing the rough-0.8 contract
  that was bound to the unsatisfiable scene.

## Impact

- `sim2policy/src/sim2policy/g1_forward_env.py` — scene override at registration; new package data
  file for the scene XML; height-field construction at model build.
- `sim2policy/src/sim2policy/config.py` (or the MJX config validator) — the feasibility invariant.
- `sim2policy/configs/g1_forward_rough_mjx.yaml`, `sim2policy/configs/showcase_training_matrix.yaml`
  — new authorization mode, campaign ID, and matrix digest.
- `sim2policy/tests/test_g1_forward_env.py`, `test_showcase_matrix.py`, `test_config.py` — extent,
  resolution, amplitude, and invariant coverage.
- Runtime image rebuild (new `mjx-{git_sha}` tag) and a bounded GPU probe before any campaign.
- No SaaS backend, frontend, curation, or GitOps change. No change to any published artifact.
- Model cost of the larger field: 768 × 768 float32 ≈ 2.4 MB, one-time at model build. MuJoCo
  height-field collision only tests cells local to the contacting geom, so per-step cost is
  expected to be unchanged — to be confirmed by the bounded probe.
