## ADDED Requirements

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
The system SHALL render initial, intermediate, and final policy checkpoints and SHALL create a labeled side-by-side or sequential montage that preserves the source videos and identifies each training stage.

#### Scenario: Standard progression exists
- **WHEN** initial, approximately 25%-progress, and final checkpoints are available
- **THEN** the montage command creates individual rollout videos and one labeled progression video beneath the run's video artifacts

#### Scenario: Exact quarter checkpoint is absent
- **WHEN** no checkpoint exists at exactly 25 percent of the training budget
- **THEN** the command selects the nearest completed checkpoint and records the actual training step in the label and media metadata
