# custom-robot-training-preparation Specification

## Purpose
Gate custom robot training behind a bounded, server-run preparation stage that proves a narrow
V1-eligible setup compiles, simulates, renders, and trains for a short smoke cycle before Start
training is ever enabled — with no per-robot image build and no tenant-controlled execution input.

## Requirements
### Requirement: Narrow V1 preparation eligibility
The system SHALL offer training preparation only for an active tenant-owned validated setup whose robot is declared `biped` or `quadruped`, whose task is `stand-balance` or `walk-forward`, whose scene is `flat-arena` or `ramp-course`, and whose tenant-selected object list is empty. The server-owned ramp intrinsic to Ramp Course SHALL NOT count as an optional object. Other valid saved setups SHALL remain usable as drafts and SHALL return a stable, human-readable training-ineligibility reason.

#### Scenario: Eligible setup can be prepared
- **WHEN** an owner requests preparation for a validated quadruped Walk Forward setup on Ramp Course with no optional objects
- **THEN** the service accepts the preparation request and derives all execution settings server-side

#### Scenario: Optional object prevents preparation
- **WHEN** an owner requests preparation for an otherwise eligible setup containing an optional catalog object
- **THEN** the service rejects the request before input publication or remote job creation and identifies that V1 custom training does not support optional objects

#### Scenario: Wider beta setup stays saved
- **WHEN** a tenant owns a validated Recover from Fall or Hurdle Course setup
- **THEN** it remains visible as a validated draft but reports `training_readiness=ineligible` and cannot start preparation

### Requirement: Immutable server-selected preparation inputs
The service SHALL read the owned robot XML and canonical setup from durable persistence, write size-bounded exact snapshots plus an input manifest beneath a server-generated preparation prefix, and pass only opaque server identities and resolved configuration to the worker. The input manifest SHALL contain schema and profile versions, immutable runtime image digest, robot/setup identifiers and SHA-256 digests, byte sizes, robot declaration, adapter/reward versions, and canonical task/scene selection. No tenant request SHALL select an object key, URL, image, command, environment variable, secret, platform, preset, or entrypoint.

#### Scenario: Server publishes a preparation snapshot
- **WHEN** an eligible preparation request is accepted
- **THEN** `robot.xml`, `normalized-setup.json`, and `input-manifest.json` are written beneath `sim2policy/preparations/<preparation-id>/inputs/` with server-derived names and matching digests

#### Scenario: Caller attempts to select runtime input
- **WHEN** a preparation request includes an unknown storage key, URL, image, command, resource, or environment field
- **THEN** validation rejects the request and no local attempt or remote resource is created

#### Scenario: Worker observes a digest mismatch
- **WHEN** a downloaded preparation input differs from its manifest digest or declared size
- **THEN** the worker stops before MuJoCo compilation and publishes a sanitized input-integrity failure

### Requirement: Content-bound preparation fingerprint
The service SHALL compute a preparation fingerprint from the robot digest, normalized setup digest, runtime image digest, adapter/reward schema versions, and preparation-profile version. Only an accepted attempt for the exact fingerprint SHALL make the setup ready for training. Any material fingerprint change SHALL require a new preparation before another training job can start.

#### Scenario: Identical preparation is idempotent
- **WHEN** the owner repeats Prepare for a fingerprint that is already non-terminal or accepted
- **THEN** the API returns that attempt and does not create a duplicate remote job

#### Scenario: Runtime update invalidates acceptance
- **WHEN** the configured immutable runtime digest changes after a setup was accepted
- **THEN** the setup returns `training_readiness=not_prepared` for new jobs until the new fingerprint is accepted

#### Scenario: Historical job retains old fingerprint
- **WHEN** an adapter or setup version changes after a custom training job completed
- **THEN** the completed job keeps its original fingerprint, input snapshot, and authorized results unchanged

### Requirement: Bounded asynchronous preparation job
Preparation SHALL run outside the SaaS API process as a Serverless AI CPU job using the immutable generic MuJoCo/SB3 runtime, a versioned server-owned preparation profile, an allowlisted `cpu-d3` preset, and hard CPU, memory, disk, input-size, phase, and wall-time limits. It SHALL NOT execute uploaded code, shell-interpolate XML, fetch tenant URLs, build an image, or accept arbitrary assets.

#### Scenario: Preparation runs on the generic runtime
- **WHEN** an eligible input snapshot is submitted in production
- **THEN** the remote job uses the configured immutable SB3 image, preparation entrypoint, allowlisted `cpu-d3` shape, bounded timeout, and server-selected input prefix

#### Scenario: Compilation exceeds its bound
- **WHEN** MuJoCo parsing or compilation does not finish within its phase deadline
- **THEN** the worker is terminated within the overall deadline and the attempt becomes failed with a sanitized compilation-timeout reason

#### Scenario: No image is built for an upload
- **WHEN** different tenants prepare different accepted MJCF robots
- **THEN** every attempt references the same configured immutable runtime digest and no per-robot build operation occurs

### Requirement: Preparation validates the complete trusted execution path
The preparation worker MUST verify the input manifest, reapply the secure MJCF/training allowlists, compose the server-owned scene, compile with the pinned MuJoCo version, validate finite compiled dynamics and bounded dimensions/control spaces, run deterministic resets, run bounded zero/random-action rollouts, render and probe a headless frame or clip, check the Gymnasium/SB3 environment contract, and complete a short PPO learn/save/reload/deterministic-evaluation cycle. Acceptance SHALL require every mandatory phase and a readable checksummed preparation report. Preparation acceptance SHALL mean execution compatibility, not guaranteed task convergence.

#### Scenario: Complete preparation passes
- **WHEN** all mandatory gates pass and the final report is readable and matches its expected fingerprint
- **THEN** the attempt becomes `accepted`, the setup becomes `training_readiness=ready`, and Start training is enabled

#### Scenario: State becomes non-finite
- **WHEN** any reset, rollout, learning, or evaluation step produces a NaN, infinity, or configured runaway value
- **THEN** preparation fails in the appropriate simulation phase and training remains disabled

#### Scenario: Short PPO path cannot reload
- **WHEN** the smoke checkpoint cannot be loaded into a clean instance with the recorded observation/action schemas
- **THEN** preparation fails and cannot be accepted based only on successful XML compilation

#### Scenario: Preparation passes but learning threshold is absent
- **WHEN** every compatibility gate passes but the short smoke policy does not reach the final training success criterion
- **THEN** the setup may still become ready and the UI explains that preparation does not guarantee training success

### Requirement: Durable preparation lifecycle and safe retry
The service SHALL persist tenant-scoped preparation attempts with states, phase, timestamps, fingerprint, input-manifest identity, immutable image/profile versions, remote job identity, last successful phase, and sanitized terminal reason. Active attempts SHALL resume reconciliation after SaaS restart. A failed attempt MAY be retried as a new attempt for the same fingerprint; at most one non-terminal attempt per setup/fingerprint and the configured per-tenant preparation concurrency/quota SHALL be enforced atomically before remote creation.

#### Scenario: SaaS restarts during preparation
- **WHEN** the backend restarts while a remote preparation job is non-terminal
- **THEN** it resumes polling the stored remote identity without creating a second job

#### Scenario: User retries a failed operational attempt
- **WHEN** an owned preparation failed terminally and the owner selects Retry
- **THEN** the service creates a new attempt for the same fingerprint subject to quota and preserves the failed attempt for diagnosis

#### Scenario: Concurrent duplicate requests race
- **WHEN** two Prepare requests for the same setup/fingerprint arrive concurrently
- **THEN** durable uniqueness and transaction boundaries allow at most one non-terminal attempt and at most one remote creation

### Requirement: Preparation failure is tenant-safe and actionable
Public preparation responses and logs SHALL expose only allowlisted phase codes and sanitized bounded diagnostics. They MUST NOT expose XML content, credentials, secret selectors, tenant identifiers, absolute paths, bucket keys, raw provider responses, or stack traces. Cross-tenant identifiers SHALL return 404, and a failed or stale preparation SHALL never enable training.

#### Scenario: Compiler produces a verbose error
- **WHEN** MuJoCo returns an error containing a local path or model content
- **THEN** the tenant sees a bounded preparation phase/reason with unsafe details removed

#### Scenario: Another tenant requests preparation state
- **WHEN** an authenticated tenant uses a setup or preparation identifier owned by another tenant
- **THEN** the API returns 404 and reveals no state, fingerprint, or remote identity

#### Scenario: Preparation report never finalizes
- **WHEN** a remote preparation succeeds but its required report remains missing or invalid past the bounded finalization deadline
- **THEN** the attempt becomes failed in finalization and Start training remains disabled
