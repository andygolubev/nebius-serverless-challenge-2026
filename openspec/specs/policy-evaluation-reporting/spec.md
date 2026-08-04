# policy-evaluation-reporting Specification

## Purpose
Judge trained policies honestly and reproducibly: deterministic multi-seed evaluation with
environment-specific success criteria, machine-readable `metrics.json`, a human-readable report
with reward curve and time-to-threshold, measured (never invented) resource/cost figures, and a
disclosed-context comparison between the Track A and Track B backends.
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

### Requirement: Deterministic checkpoint progression and selection
For a run eligible for public curation, the system SHALL record a structured progression document
covering the initial checkpoint, evaluated intermediate candidates, and selected checkpoint. Each
entry SHALL contain exact training step, checkpoint digest, deterministic seed set, per-episode and
aggregate task metrics, configured criterion, success result, evaluation runtime, and associated
rollout identity. Checkpoint selection SHALL use task metrics and a selection seed set disjoint from
final acceptance; it MUST NOT assume the final step or highest scalar reward is the best policy.

#### Scenario: Locomotion checkpoints are ranked
- **WHEN** multiple G1 checkpoints are evaluated for curation
- **THEN** they are ranked first by full-horizon no-termination episode count, then minimum forward
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
- **THEN** only the single selected checkpoint is evaluated on the separate final acceptance seeds
  and the promotion record names that checkpoint and its result

#### Scenario: G1 environment terminates an episode
- **WHEN** a G1 rollout ends before the configured horizon
- **THEN** the per-episode evidence distinguishes torso inversion, foot-foot contact, foot-shin
  contact, NaN state, and unknown environment termination, retains every observed cause, and does not
  reduce all outcomes to the label `fall`

### Requirement: Measured curriculum provenance
The system SHALL, when a policy is trained through multiple curriculum phases, record in
`metrics.json`, the resolved configuration, and the human report each phase's canonical
environment, immutable configuration revision, step budget, input/selected checkpoint digest,
measured runtime/cost, and phase-specific evaluation. The final success result SHALL describe the
final task only and SHALL not inherit a prerequisite phase's success.

#### Scenario: Flat-to-rough G1 curriculum completes
- **WHEN** a flat-terrain checkpoint is resumed into rough-terrain training
- **THEN** the final evidence records both phases, the immutable pre-resume transition record, and
  the exact parent object, step, digest, observation-normalizer, policy, and value parameters
  actually loaded by the rough trainer; it also records fresh optimizer/learner/RNG initialization
  while scoring public success only against the rough-terrain acceptance gate

#### Scenario: Recovery would choose a different flat checkpoint
- **WHEN** finalization-only recovery re-evaluation would rank a different flat checkpoint than the
  immutable transition record
- **THEN** the recorded transition remains authoritative and recovery cannot replace or rewrite it

#### Scenario: Prerequisite passes but final task fails
- **WHEN** the flat gait phase passes and the rough phase remains unstable
- **THEN** the report shows the prerequisite success and final failure separately and the run is not
  eligible for public promotion

