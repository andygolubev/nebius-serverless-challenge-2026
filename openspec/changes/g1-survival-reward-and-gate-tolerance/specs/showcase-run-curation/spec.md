## MODIFIED Requirements

### Requirement: Reviewed fixed-forward H100 G1 recovery
The G1 recovery SHALL align training with the public Walk Forward acceptance task by using
server-owned phase-specific fixed-forward environments. Flat SHALL keep `[1.0, 0.0, 0.0]` while
rough SHALL keep `[0.8, 0.0, 0.0]` for the full 1,000-step episode; pushes SHALL remain disabled and
the reviewed PPO, physics, reset, observation, action, and termination settings SHALL remain
unchanged apart from the reviewed survival reward (`alive` 0.25) and discount factor (0.99). Rough
training and evaluation SHALL run on the server-owned 60 m x 60 m rough-terrain scene. The workflow
SHALL retain the timed-out sweep, the terminal first fixed-forward result, and the exhausted
`user_reviewed_rough_08_full_v2` authorization, none of which SHALL be reused or extended. It SHALL
authorize exactly one new fresh seed-0, non-preemptible H100 curriculum job only under a new
reviewed mode bound to the enlarged scene, the survival reward, and the gate tolerance below, with a
450M effective-step ceiling and five-hour timeout. Each phase SHALL round down to whole PPO epoch
quanta and the measured combined spend SHALL NOT exceed that ceiling.

Because rollouts are sampled rather than bit-reproducible, gates SHALL state a tolerance. The flat
transition gate SHALL require **9 of 10** selection episodes to reach the 1,000-step horizon without
termination. Final publication SHALL require **18 of 20** 1,000-step episodes without any
environment termination. Every **completed** episode SHALL average at least 0.4 m/s, and the
preferred mean SHALL be at least 0.6 m/s.

#### Scenario: Flat gate tolerates one sampled failure
- **WHEN** 9 of 10 flat selection episodes reach the horizon without termination and every completed
  episode averages at least 0.4 m/s
- **THEN** the flat gate passes and rough training receives the remaining measured budget

#### Scenario: Flat gate still fails on a genuinely unreliable gait
- **WHEN** 8 or fewer of 10 flat selection episodes reach the horizon
- **THEN** rough training is not started, selection evidence is persisted without evaluating reserved
  final seeds, cleanup runs, and the campaign stops at needs-human

#### Scenario: A terminated episode is not counted twice
- **WHEN** an episode terminates early and therefore records a negative or low mean velocity
- **THEN** it fails the gate as a missing horizon only, and its velocity is excluded from the
  minimum-velocity statistic rather than reported as a separate velocity failure

#### Scenario: Final acceptance tolerates two sampled failures
- **WHEN** 18 or more of 20 final episodes reach the horizon without termination, every completed
  episode averages at least 0.4 m/s, and the mean is at least 0.6 m/s
- **THEN** the checkpoint passes hard acceptance and may be pinned

#### Scenario: Exhausted or pre-reward authorization is not reused
- **WHEN** a new G1 campaign is planned after `user_reviewed_rough_08_full_v2` was spent, or under
  any mode predating the survival reward and gate tolerance
- **THEN** planning requires a new reviewed mode, campaign ID, and matrix digest bound to the
  enlarged scene, the survival reward, the discount factor, and the tolerance, and refuses the old
  mode

#### Scenario: Rough authorization drifts
- **WHEN** the mode, campaign ID, phase command, seed, job allowance, phase budget, hardware,
  timeout, image, revision, matrix digest, scene extent, survival reward, discount factor, or gate
  tolerance differs from the reviewed contract
- **THEN** planning or preflight fails before submission and no pilot evidence is synthesized

#### Scenario: Fresh flat gait passes at the exact phase boundary
- **WHEN** the fresh result campaign's uninterrupted quantum-aligned nominal-200M flat checkpoint
  (199,229,440 effective steps under the reviewed batch contract) satisfies the flat gate above and
  the next phase can restore its observation-normalizer, policy, and value parameters
- **THEN** an immutable transition record is published and rough training receives the remaining
  measured budget up to the 450M ceiling

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

### Requirement: Gate tolerance is justified against measured reliability
A curated locomotion gate SHALL record the per-episode reliability it assumes and the resulting
probability that a policy meeting that reliability passes. A gate whose pass probability falls below
50% for a policy at the assumed reliability SHALL NOT be authorized, so that a campaign is never
funded against a bar it is unlikely to clear even when the policy is good enough.

#### Scenario: A gate is authorized
- **WHEN** a G1 campaign authorization is planned
- **THEN** it records the assumed per-episode reliability and the computed pass probability for the
  flat and final gates, and planning fails if either falls below 50%

#### Scenario: An all-or-nothing gate is proposed
- **WHEN** a gate requires every sampled episode to succeed
- **THEN** planning fails, because sampled evidence cannot support an exact-count requirement
