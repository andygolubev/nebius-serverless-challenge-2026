# rollout-media Specification

## Purpose
Turn checkpoints into watchable evidence: deterministic policy rollouts encoded as MP4s, headless
rendering that tries EGL first and retries once with OSMesa in a fresh process, a no-checkpoint
render smoke test for container preflight, and a labeled initial/mid/final progression montage.
## Requirements
### Requirement: Deterministic checkpoint rollout
The system SHALL load a supported backend checkpoint, run deterministic policy inference with an explicit seed, render RGB frames across episode boundaries, and encode a playable MP4 at configurable duration and frame rate.

#### Scenario: Rollout reaches an episode boundary
- **WHEN** the environment terminates or truncates before the requested video duration
- **THEN** the renderer resets with a deterministic next seed and continues until the requested frame count is produced

#### Scenario: Unsupported checkpoint is supplied
- **WHEN** checkpoint metadata identifies an unsupported backend or mismatched environment
- **THEN** rendering exits with a compatibility diagnostic and does not emit a misleading video

### Requirement: Headless rendering fallback
The renderer SHALL attempt EGL headless rendering first by default and SHALL retry once in a fresh process using OSMesa when graphics initialization fails.

#### Scenario: EGL is available
- **WHEN** EGL initializes and produces frames
- **THEN** the renderer completes without invoking the OSMesa fallback

#### Scenario: EGL initialization fails
- **WHEN** EGL cannot initialize in the container
- **THEN** the renderer starts a fresh OSMesa render process and reports which backend produced the output

### Requirement: Rendering smoke test
The system SHALL provide a smoke command that renders and validates at least ten frames without requiring a trained checkpoint.

#### Scenario: Container render preflight
- **WHEN** an operator runs the render smoke command in a built image
- **THEN** the command verifies frame dimensions and encoding and exits non-zero on graphics or codec failure

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

