## ADDED Requirements

### Requirement: Deterministic checkpoint progression and selection
For a run eligible for public curation, the system SHALL record a structured progression document
covering the initial checkpoint, evaluated intermediate candidates, and selected checkpoint. Each
entry SHALL contain exact training step, checkpoint digest, deterministic seed set, per-episode and
aggregate task metrics, configured criterion, success result, evaluation runtime, and associated
rollout identity. Checkpoint selection SHALL use task metrics and a selection seed set disjoint from
final acceptance; it MUST NOT assume the final step or highest scalar reward is the best policy.

#### Scenario: Locomotion checkpoints are ranked
- **WHEN** multiple G1 checkpoints are evaluated for curation
- **THEN** they are ranked first by full-horizon no-fall episode count, then minimum forward
  velocity, mean episode length, and mean velocity, with exact values retained

#### Scenario: Mean-reward checkpoints are ranked
- **WHEN** multiple SB3 checkpoints are evaluated for curation
- **THEN** they are ranked by the configured deterministic mean-reward criterion with seed and
  evaluation context retained

#### Scenario: Final checkpoint regresses
- **WHEN** the final-step checkpoint performs worse than an earlier evaluated checkpoint
- **THEN** the earlier checkpoint may be selected and the final regression remains present in the
  progression document

#### Scenario: Selected checkpoint receives final acceptance
- **WHEN** checkpoint selection completes
- **THEN** only the bounded shortlist is evaluated on the separate final acceptance seeds and the
  promotion record names the checkpoint that passed

### Requirement: Measured curriculum provenance
The system SHALL, when a policy is trained through multiple curriculum phases, record in
`metrics.json`, the resolved configuration, and the human report each phase's canonical
environment, immutable configuration revision, step budget, input/selected checkpoint digest,
measured runtime/cost, and phase-specific evaluation. The final success result SHALL describe the
final task only and SHALL not inherit a prerequisite phase's success.

#### Scenario: Flat-to-rough G1 curriculum completes
- **WHEN** a flat-terrain checkpoint is resumed into rough-terrain training
- **THEN** the final evidence records both phases and the exact parent digest while scoring public
  success only against the rough-terrain acceptance gate

#### Scenario: Prerequisite passes but final task fails
- **WHEN** the flat gait phase passes and the rough phase remains unstable
- **THEN** the report shows the prerequisite success and final failure separately and the run is not
  eligible for public promotion
