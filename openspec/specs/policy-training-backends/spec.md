# policy-training-backends Specification

## Purpose
TBD - created by archiving change implement-sim2policy. Update Purpose after archive.
## Requirements
### Requirement: Validated run configuration
The system SHALL load a YAML run configuration containing the backend, environment, seed, training budget, parallelism, checkpoint cadence, evaluation settings, and success criterion, SHALL apply supported CLI overrides deterministically, and SHALL reject invalid or incompatible values before training starts.

#### Scenario: Valid configuration is resolved
- **WHEN** a user starts training with a valid environment configuration and supported CLI overrides
- **THEN** the system starts the selected backend with a resolved configuration and writes that configuration into the run metadata

#### Scenario: Invalid configuration is rejected early
- **WHEN** required values are missing or a setting is incompatible with the selected backend
- **THEN** the command exits with a diagnostic before creating an environment or beginning training

### Requirement: Stable-Baselines3 baseline training
The system SHALL train supported Gymnasium MuJoCo environments with Stable-Baselines3 PPO, SHALL support at least HalfCheetah and Ant configurations, and SHALL use recorded environment-specific hyperparameters rather than untracked runtime defaults.

#### Scenario: HalfCheetah baseline run
- **WHEN** a user selects the HalfCheetah SB3 configuration
- **THEN** the system creates the configured vectorized environments, trains PPO for the requested timestep budget, and produces initial, periodic, and final checkpoints

### Requirement: GPU-native MJX training
The system SHALL provide an opt-in MuJoCo MJX locomotion training path using the pinned MuJoCo Playground/Brax PPO integration and SHALL emit run metadata and checkpoints under the same run conventions as the SB3 path.

#### Scenario: MJX quadruped run
- **WHEN** a user selects a supported MJX configuration on a compatible GPU image
- **THEN** the system trains the configured policy with parallel GPU simulation and publishes backend-identifiable checkpoints and metadata

#### Scenario: MJX dependencies are unavailable
- **WHEN** the MJX command runs in an image without its optional dependency group
- **THEN** the command exits with an actionable dependency/image diagnostic without affecting availability of SB3 commands

### Requirement: Reproducibility metadata
The system SHALL record run ID, backend, environment, seed, resolved configuration, package versions, device details, timestamps, and source revision when available without recording credentials.

#### Scenario: Run metadata is inspected
- **WHEN** a training run initializes
- **THEN** a machine-readable metadata file contains the inputs needed to identify and reproduce the run and excludes storage or cloud secrets

### Requirement: Backend isolation
The SB3 workflow SHALL remain buildable, testable, and runnable without installing the MJX/JAX dependency group.

#### Scenario: SB3-only installation
- **WHEN** a user installs or builds only the SB3 dependency target
- **THEN** SB3 training, evaluation, rendering, and storage features work without importing MJX-specific packages

