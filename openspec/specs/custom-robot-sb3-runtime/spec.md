# custom-robot-sb3-runtime Specification

## Purpose
Provide one generic, server-owned SB3/MuJoCo environment runtime that composes any accepted
uploaded robot into a fixed scene and task contract, so custom training never requires a
per-robot image, tenant world code, or tenant-selected hyperparameters.

## Requirements
### Requirement: Server-owned scene composition and training allowlist
The generic runtime SHALL compose the validated single floating robot subtree into a versioned server-owned Flat Arena or Ramp Course and SHALL own gravity, timestep bounds, floor/ramp geometry, contact defaults, lights, cameras, reset distribution, episode horizon, reward, termination, and evaluation rules. Training eligibility SHALL require the bounded primitive-geometry contract, supported compiled finite dynamics, supported hinge joints, and explicit finite motor actuator control ranges. Tenant world floors, scene obstacles, simulation overrides, cameras, lights, sensors as policy inputs, external assets, and unsupported compiled features SHALL NOT affect the executable V1 environment.

#### Scenario: Ramp scene is composed
- **WHEN** a prepared setup selects Ramp Course
- **THEN** the worker attaches the robot to the exact versioned server ramp scene and records the scene version and parameters in resolved configuration

#### Scenario: Uploaded world tries to alter the task
- **WHEN** an otherwise upload-valid MJCF contains a tenant world floor, light, camera, or simulation option outside the executable robot subtree contract
- **THEN** preparation rejects it as training-ineligible or deterministically excludes it according to the published adapter schema, rather than silently changing the task

#### Scenario: Actuator lacks a usable control range
- **WHEN** a compiled action-producing actuator has an unsupported type or no finite bounded control range
- **THEN** preparation fails before rollout with an actuator-contract reason

### Requirement: Deterministic generic observation and action schemas
For each accepted robot, the runtime SHALL derive and record a deterministic ordered observation schema containing versioned root pose/orientation features, root linear/angular velocity features, normalized actuated-joint position/velocity features, previous action, and task target, and an action schema containing one normalized continuous value per eligible motor actuator. Actions SHALL be clipped to `[-1, 1]` and mapped to verified finite control ranges. Resets and evaluations SHALL use recorded server-owned seeds, and every numeric observation, reward, action, and state bound SHALL be checked for finiteness.

#### Scenario: Same fingerprint produces the same spaces
- **WHEN** preparation and training load the same fingerprint in the same runtime digest
- **THEN** they derive identical observation/action dimensions, ordering, normalization, bounds, and schema hashes

#### Scenario: Robot action dimensions differ
- **WHEN** two accepted robots have different numbers of eligible actuators
- **THEN** each job receives its own deterministic action dimension while still using the same generic runtime image and fixed PPO profile schema

#### Scenario: Action exceeds normalized bounds
- **WHEN** PPO or evaluation supplies an action outside `[-1, 1]`
- **THEN** the adapter applies its recorded clipping/mapping rule without sending a non-finite or out-of-range control to MuJoCo

### Requirement: Fixed Stand Balance task contract
The `stand-balance` adapter SHALL use versioned server-owned reset, reward, termination, and success definitions based on upright orientation, target root height, bounded root motion, action/energy penalties, non-finite/runaway protection, fall conditions, and a fixed episode horizon. All coefficients and thresholds SHALL be present in resolved configuration and final metrics.

#### Scenario: Stable standing episode is scored
- **WHEN** an evaluation episode remains upright near the target height within the configured motion bounds
- **THEN** its task metrics and success value are calculated from the recorded Stand Balance contract

#### Scenario: Robot falls
- **WHEN** root height or orientation crosses the configured fall threshold
- **THEN** the episode terminates with a recorded fall reason and no invented success

### Requirement: Fixed Walk Forward task contract
The `walk-forward` adapter SHALL use versioned server-owned reset, reward, termination, and success definitions based on target forward velocity/progress, upright orientation, lateral/yaw control, action/energy penalties, non-finite/runaway protection, fall conditions, and a fixed episode horizon. All coefficients and thresholds SHALL be present in resolved configuration and final metrics.

#### Scenario: Forward locomotion is evaluated
- **WHEN** a deterministic evaluation episode completes without falling
- **THEN** the report records forward velocity/progress, lateral drift, upright/fall measures, reward terms, and success under the versioned Walk Forward criterion

#### Scenario: Fast sideways motion is not reported as walking success
- **WHEN** a policy moves rapidly but violates the configured forward-direction, lateral, upright, or fall criterion
- **THEN** the episode is not counted as successful solely because its scalar reward is high

### Requirement: Fixed custom PPO quick training profile
An accepted setup SHALL start only the server-owned `custom-ppo-quick` profile using the immutable generic SB3 runtime on an allowlisted `cpu-d3` preset. Backend, algorithm, PPO hyperparameters, vector-environment count, total timesteps, evaluation cadence/seeds, checkpoint cadence, disk, timeout, and artifact settings SHALL be fixed in a versioned resolved job specification and SHALL NOT be tenant-editable. Production enablement SHALL require benchmark evidence that freezes a bounded profile for all eight canonical biped/quadruped, task, and scene combinations.

#### Scenario: Owner starts an accepted setup
- **WHEN** the owner starts training from the latest accepted fingerprint
- **THEN** the service creates a normal custom-robot Job with `backend=sb3`, `profile=custom-ppo-quick`, the allowlisted `cpu-d3` job spec, and the exact accepted input references

#### Scenario: User supplies a backend or hyperparameter
- **WHEN** a custom training request includes backend, algorithm, hardware, image, command, timestep, learning-rate, or environment overrides
- **THEN** validation rejects the request and no job is created

#### Scenario: Setup is merely validated
- **WHEN** a setup has no current accepted preparation fingerprint
- **THEN** Start training is refused before local or remote job creation

### Requirement: Idempotent setup-bound training creation
Custom training SHALL be created through a tenant-owned setup-bound API and persisted as a normal Job linked to robot, setup, preparation attempt, fingerprint, input manifest, runtime digest, adapter/reward versions, and fixed profile. The service SHALL enforce an idempotency key or equivalent atomic active-job guard and configured per-tenant concurrency/start quotas before remote submission. Custom setups SHALL NOT appear as public `/training-options` entries.

#### Scenario: Double-click does not create two jobs
- **WHEN** the browser repeats the same Start training request while creation is in progress
- **THEN** the API returns the same Job or a stable conflict and creates at most one remote job

#### Scenario: Tenant capacity is occupied
- **WHEN** the owner reaches the configured active custom-training limit
- **THEN** the API returns actionable bounded retry guidance before creating a local Job or remote resource

#### Scenario: Public catalog is requested
- **WHEN** any tenant fetches `/training-options`
- **THEN** no private robot/setup or generic custom profile is exposed as a public gallery option

### Requirement: Immutable run input snapshot
Before remote training starts, the service SHALL copy or content-address the accepted robot XML, normalized setup, and input manifest beneath the server-generated run prefix and SHALL verify that their digests equal the accepted preparation fingerprint. Training SHALL stop before environment creation if the snapshot is absent, oversized, unsafe, or mismatched. Soft deletion of the source robot/setup SHALL prevent new starts but SHALL NOT break an already-created historical job.

#### Scenario: Accepted source changes before start
- **WHEN** the resolved robot/setup/runtime fingerprint no longer matches the accepted preparation at Start training time
- **THEN** job creation is refused and the user is instructed to prepare the current setup

#### Scenario: Source is deleted after job creation
- **WHEN** an owner soft-deletes the original robot or setup after a custom Job has its immutable run snapshot
- **THEN** the Job continues and its authorized results remain reproducible from the snapshot

### Requirement: Normal evaluation and result finalization
A custom training Job SHALL use the normal non-terminal lifecycle and SHALL become `completed` only after a load-tested final checkpoint, deterministic multi-seed task evaluation, per-episode and aggregate metrics, human-readable summary and reward curve, final rollout MP4, resolved configuration/runtime metadata, validated artifact manifest, and custom policy bundle are readable and valid. Reaching the task success threshold SHALL be reported honestly but SHALL NOT be required for artifact-complete job completion.

#### Scenario: Training finishes below threshold
- **WHEN** the fixed training budget completes and every required artifact is valid but evaluation misses the task success threshold
- **THEN** the Job becomes completed with `success=false`, measured results, and rollout evidence rather than being mislabeled as infrastructure failure

#### Scenario: Required rollout is missing
- **WHEN** training and evaluation finish but the final MP4 is absent or invalid past the bounded finalization deadline
- **THEN** the Job fails in finalization and is not exposed as a completed result

#### Scenario: Custom job completes normally
- **WHEN** every required custom result and manifest entry is readable and valid
- **THEN** the existing Jobs dashboard and result API expose the custom Job like a normal owned training job
