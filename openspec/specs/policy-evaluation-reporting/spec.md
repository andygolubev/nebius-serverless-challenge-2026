# policy-evaluation-reporting Specification

## Purpose
TBD - created by archiving change implement-sim2policy. Update Purpose after archive.
## Requirements
### Requirement: Deterministic multi-seed evaluation
The system SHALL evaluate a checkpoint with deterministic inference over a configurable episode count and seed set, defaulting to 20 episodes distributed across five seeds, and SHALL retain per-episode reward and length values.

#### Scenario: Default evaluation completes
- **WHEN** a user evaluates a compatible checkpoint without overriding evaluation settings
- **THEN** the system runs 20 deterministic episodes across five seeds and records every episode result

### Requirement: Environment-specific success criteria
The system SHALL obtain the success criterion from the resolved environment configuration and SHALL calculate aggregate success without assuming that every backend uses the same reward semantics.

#### Scenario: Reward-threshold environment is evaluated
- **WHEN** an SB3 environment defines a mean-reward threshold
- **THEN** the report states the threshold and whether the aggregate mean reward meets it

#### Scenario: Locomotion-criterion environment is evaluated
- **WHEN** an MJX environment defines sustained velocity and non-fall conditions
- **THEN** each episode and the aggregate report are scored using those configured conditions

### Requirement: Machine-readable metrics
The system SHALL write `report/metrics.json` containing checkpoint identity, backend, environment, seeds, episode measurements, aggregate mean and standard deviation, success result, threshold definition, runtime, and available device/version metadata.

#### Scenario: Metrics are consumed by another command
- **WHEN** evaluation completes successfully
- **THEN** the metrics document conforms to the documented schema without requiring console-output parsing

### Requirement: Human-readable report and reward curve
The system SHALL generate a Markdown summary and a reward-curve image from run logs, and SHALL identify wall-clock time to the configured success threshold when the logged data crosses it.

#### Scenario: Training crosses the threshold
- **WHEN** logged evaluations first meet the configured success criterion
- **THEN** the report includes the first crossing step and elapsed wall-clock time and links the generated reward curve

#### Scenario: Training never crosses the threshold
- **WHEN** no logged evaluation meets the success criterion
- **THEN** the report explicitly records that the threshold was not reached within the training budget

### Requirement: Honest resource and cost reporting
The system SHALL accept measured utilization and an explicit timestamped rate input, SHALL calculate estimated cost as runtime multiplied by the applicable rate, and MUST mark unavailable inputs instead of inventing values.

#### Scenario: Complete cost inputs are supplied
- **WHEN** runtime, GPU resource identity, utilization data, hourly rate, currency, and rate date are available
- **THEN** the report includes utilization and a reproducible cost-per-policy calculation

#### Scenario: Price or utilization is unavailable
- **WHEN** optional benchmark inputs are absent
- **THEN** the corresponding report fields are marked unavailable and no synthetic estimate is shown

### Requirement: Backend comparison
The system SHALL generate a comparison table from compatible Track A and Track B metrics documents and SHALL disclose environment, budget, seed, hardware, version, and success-criterion differences.

#### Scenario: Two compatible reports are compared
- **WHEN** a user supplies completed metrics for both backends
- **THEN** the comparison reports time-to-threshold, total runtime, success, utilization, and cost where available with all material run context

