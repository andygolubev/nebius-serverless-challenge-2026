## ADDED Requirements

### Requirement: Reviewed survival reward for fixed-forward G1
The fixed-forward G1 identities SHALL train with a positive `alive` reward scale of 0.25 and a
`discounting` of 0.99. The pinned upstream `termination` scale of −100.0 SHALL remain unchanged so
that the survival signal changes in one reviewed dimension rather than two. The value 0.25 is the
scale the pinned Playground 0.2.0 T1 humanoid uses, and SHALL NOT be raised to a level at which
standing still outscores walking under the declared forward command.

#### Scenario: Fixed-forward G1 configs declare the survival reward
- **WHEN** the fixed-forward G1 flat or rough configuration is resolved
- **THEN** it declares `reward_config.scales.alive` of 0.25 and `discounting` of 0.99, and leaves the
  termination scale, physics, reset, observation, action, and termination predicate unchanged

#### Scenario: Walking still outscores standing under the forward command
- **WHEN** the survival reward is combined with the pinned velocity-tracking reward at the declared
  forward command
- **THEN** the per-step return for tracking the command exceeds the per-step return for standing
  still by at least a factor of three, so surviving cannot become a cheaper policy than the task

#### Scenario: Survival reward is rejected when it would dominate the task
- **WHEN** an `alive` scale is configured at which standing still would score within that margin of
  walking
- **THEN** validation fails before any GPU step rather than training a policy that can stand still
  for reward

### Requirement: Closed Playground override allowlist admits the survival reward
`playground_config_overrides` SHALL continue to reject every key outside a reviewed allowlist, and
that allowlist SHALL contain exactly `push_config.enable` and `reward_config.scales.alive`. Reward
editing beyond that single scale SHALL remain unavailable through configuration.

#### Scenario: Reviewed reward override is accepted
- **WHEN** a configuration sets `reward_config.scales.alive` to a number
- **THEN** the configuration resolves and the scale reaches the environment

#### Scenario: Unreviewed reward override is rejected
- **WHEN** a configuration sets any other `reward_config.scales.*` key, or any other Playground
  config path
- **THEN** validation fails naming the unsupported override, and no run is submitted
