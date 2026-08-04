## MODIFIED Requirements

### Requirement: Policy progression montage
The system SHALL render deterministic initial, evaluated intermediate, selected, and final-step
policy checkpoints and SHALL create a labeled side-by-side or sequential montage that preserves the
source videos and identifies each exact training step. For curated runs the selected checkpoint,
not merely the final-step checkpoint, SHALL supply the public final rollout. Media metadata SHALL
link each video to the corresponding checkpoint digest and structured progression metrics and SHALL
label measured regression rather than implying monotonic improvement.

#### Scenario: Standard progression exists
- **WHEN** initial, evaluated intermediate, selected, and final-step checkpoints are available
- **THEN** the montage command creates individual rollout videos and one labeled progression video
  beneath the curated run's video artifacts with exact steps and selection state

#### Scenario: Exact quarter checkpoint is absent
- **WHEN** no checkpoint exists at exactly 25 percent of the training budget
- **THEN** the command selects the nearest completed evaluated checkpoint and records its actual
  step and digest in the label and media metadata

#### Scenario: Best checkpoint is not final
- **WHEN** deterministic task metrics select an earlier checkpoint over the final-step checkpoint
- **THEN** the public final rollout uses the selected checkpoint while the montage retains the
  final-step rollout labeled as a regression

#### Scenario: Progress media lacks metrics provenance
- **WHEN** a video cannot be linked to an evaluated checkpoint step, digest, and progression record
- **THEN** it is excluded from curated progress and cannot satisfy the showcase media gate

