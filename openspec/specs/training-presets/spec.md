# training-presets Specification

## Purpose
TBD - created by archiving change add-serverless-training-api. Update Purpose after archive.
## Requirements
### Requirement: Declarative preset catalog

The system SHALL define demo training options in a declarative catalog file (`configs/training_presets.yaml`). Each preset SHALL fully specify the fixed training configuration — backend, environment, algorithm, training limits, expected artifacts — and the small set of safe, bounded parameters a demo user may override.

#### Scenario: Catalog loads and validates

- **WHEN** the API loads `configs/training_presets.yaml` at startup
- **THEN** each preset is parsed into a fixed run configuration and a set of allowed safe parameters with bounds, and a malformed or duplicate-named preset causes a clear startup error

#### Scenario: Preset resolves to an existing run config

- **WHEN** a preset is resolved for a run
- **THEN** it maps onto the project's existing run-config schema (backend, environment, training, checkpoint, evaluation, rendering, storage) without requiring any user-supplied executable input

### Requirement: Initial demo presets

The catalog SHALL include the initial demo presets: `halfcheetah-demo`, `ant-demo`, and `ant-quality`, each using the `stable-baselines3` backend with PPO; and SHALL optionally include `go1-mjx-demo` (MJX/Brax backend) behind a feature flag that is enabled only when the MJX track is supported reliably.

#### Scenario: HalfCheetah quick demo

- **WHEN** `halfcheetah-demo` is resolved
- **THEN** it targets `HalfCheetah-v5` with SB3 PPO and a short training budget suitable for a fast local/cloud smoke run producing a final checkpoint, a short rollout video, and metrics

#### Scenario: Ant demo

- **WHEN** `ant-demo` is resolved
- **THEN** it targets `Ant-v5` with SB3 PPO at a budget that yields a visually understandable walking result, producing untrained/mid/final videos, metrics, and a report

#### Scenario: Ant quality

- **WHEN** `ant-quality` is resolved
- **THEN** it targets `Ant-v5` with SB3 PPO at a longer training budget intended for a higher-quality final policy for demo recording

#### Scenario: Go1 MJX demo is gated

- **WHEN** the MJX feature flag is disabled
- **THEN** `go1-mjx-demo` is neither listed by the API nor accepted by `POST /train`; when the flag is enabled it resolves to a Go1/MuJoCo Playground quadruped on the MJX/Brax backend with PPO

### Requirement: Allowlist enforcement

The system SHALL treat the catalog as an allowlist: only presets present (and enabled) in the catalog are valid, and the resolved configuration SHALL never be overridden by arbitrary user-supplied environment IDs, images, commands, code paths, or reward functions.

#### Scenario: Only allowlisted presets are accepted

- **WHEN** a preset name is checked against the catalog
- **THEN** names not present or disabled in the catalog are rejected, and only the catalog-defined configuration is used to build the job

