## MODIFIED Requirements

### Requirement: Reviewed fixed-forward H100 G1 recovery
The G1 recovery SHALL align training with the public Walk Forward acceptance task by using
server-owned phase-specific fixed-forward environments. Flat SHALL keep `[1.0, 0.0, 0.0]` while
rough SHALL keep `[0.8, 0.0, 0.0]` for the full 1,000-step episode; pushes SHALL remain disabled and
the reviewed PPO, reward, physics, reset, observation, action, and termination settings SHALL remain
unchanged. Rough training and evaluation SHALL run on the server-owned 60 m × 60 m rough-terrain
scene, because the upstream 20 m × 20 m height field places its nearest edge 10 m from the spawn
point and cannot contain the 16 m that `[0.8, 0.0, 0.0]` implies over a 1,000-step episode. The
workflow SHALL retain the timed-out sweep, the terminal first fixed-forward result, which failed its
flat selection gate and touched no rough PPO steps, and the exhausted
`user_reviewed_rough_08_full_v2` authorization, which was bound to the unsatisfiable scene and SHALL
NOT be reused or extended. It SHALL authorize exactly one new fresh seed-0, non-preemptible H100
curriculum job only under a new reviewed mode bound to the enlarged scene, with a 450M
effective-step ceiling and five-hour timeout. Each phase SHALL round down to whole PPO epoch quanta
and the measured combined spend SHALL NOT exceed that ceiling. Final publication SHALL require 20/20
1,000-step episodes without any environment termination and at least 0.4 m/s measured forward
velocity in every episode. The preferred mean SHALL be at least 0.6 m/s.

#### Scenario: Rough gate is verified satisfiable before authorization
- **WHEN** a G1 rough authorization is planned
- **THEN** planning fails unless the rough command and horizon fit within the registered scene's
  worst-case spawn-to-edge distance, so an unreachable gate cannot be authorized

#### Scenario: Exhausted rough-0.8 authorization is not reused
- **WHEN** a new G1 campaign is planned after `user_reviewed_rough_08_full_v2` was spent on the
  20 m × 20 m scene
- **THEN** planning requires a new reviewed mode, campaign ID, and matrix digest bound to the
  enlarged scene, and refuses to run under the old mode

#### Scenario: Operator authorizes a fresh campaign on the enlarged scene
- **WHEN** the reviewed mode, campaign ID, and matrix digest name the enlarged rough scene and the
  normalized matrix declares them
- **THEN** the workflow preserves every prior job and permits exactly one fresh campaign only for the
  matrix-bound campaign ID, phase commands, seed 0, immutable revision/image/matrix, exact phase
  budgets, H100 shape, 100 GiB disk, and five-hour timeout

#### Scenario: Rough authorization drifts
- **WHEN** the mode, campaign ID, phase command, seed, job allowance, phase budget, hardware,
  timeout, image, revision, matrix digest, or scene extent differs from the reviewed contract
- **THEN** planning or preflight fails before submission and no pilot evidence is synthesized

#### Scenario: Fresh flat gait passes at the exact phase boundary
- **WHEN** the fresh result campaign's uninterrupted quantum-aligned nominal-200M flat checkpoint
  (199,229,440 effective steps under the reviewed batch contract) completes 10/10 selection episodes
  without termination, every episode averages at least 0.4 m/s, and the next phase can restore its
  observation-normalizer, policy, and value parameters
- **THEN** an immutable transition record is published and rough training receives the remaining
  measured budget up to the 450M ceiling

#### Scenario: Fresh flat gait never passes
- **WHEN** the exact derived flat phase-boundary checkpoint fails its declared gate
- **THEN** rough-terrain training is not started, selection evidence is persisted without evaluating
  reserved final seeds, cleanup runs, and the campaign stops at needs-human

#### Scenario: Brax phase boundary reinitializes learner-only state
- **WHEN** the fresh rough phase restores a pinned Brax 0.14.2 checkpoint
- **THEN** evidence proves restoration of observation-normalizer, policy, and value parameters and
  explicitly records deterministic seed-0 reinitialization of optimizer, learner step, rollout
  state, and PRNG rather than claiming full-state continuation

#### Scenario: Rough checkpoint passes before final step
- **WHEN** a retained rough checkpoint outranks later checkpoints and passes final acceptance
- **THEN** that checkpoint is the selected public policy and later regression remains visible

#### Scenario: G1 recovery exhausts its authorization
- **WHEN** the fresh 450M campaign fails its declared gate
- **THEN** the workflow launches no retry, pilot, second seed, hardware comparison, reward change, or
  extra training without a new reviewed decision

## ADDED Requirements

### Requirement: Evidence from different scene geometry is not comparable
Curated G1 evidence SHALL record the rough scene extent under which it was measured, and the
workflow SHALL NOT rank, compare, or substitute checkpoints across runs whose rough scene extents
differ. The retained recording measured on the 20 m × 20 m scene SHALL remain publishable as a
verified recording and SHALL NOT be promoted by re-evaluation on the enlarged scene.

#### Scenario: Checkpoints from different scenes are ranked together
- **WHEN** candidate checkpoints from runs with differing rough scene extents are presented for
  ranking
- **THEN** selection fails rather than producing a ranking that mixes scene geometries

#### Scenario: Retained recording stays a recording
- **WHEN** the enlarged scene is registered
- **THEN** `showcase-gallery-g1-20260801-16-g1-s0-rough` remains an operator-reviewed verified
  recording with its original below-threshold numbers, and is not re-scored or re-pinned
