# saas-nebius-orchestration Specification

## Purpose
Connect the tenant SaaS control plane to Nebius Serverless AI jobs through a preset-only,
SDK-backed orchestration adapter that persists remote job identities and reflects their lifecycle.
## Requirements
### Requirement: Nebius orchestration backend

The SaaS app SHALL provide a `nebius` orchestration backend, selected via `SAAS_ORCHESTRATION_BACKEND=nebius`, that implements the existing `OrchestrationBackend` interface without changing the tenant-facing API. The backend SHALL create Serverless AI jobs through the official Nebius Python SDK (`JobServiceClient`), not by shelling out to the CLI. The `mock` backend SHALL remain available and remain the default.

#### Scenario: Backend selected by configuration

- **WHEN** the service starts with `SAAS_ORCHESTRATION_BACKEND=nebius` and valid Nebius credentials
- **THEN** `GET /health` reports the `nebius` backend and `POST /jobs` submits real Serverless AI jobs

#### Scenario: Mock remains the default

- **WHEN** the service starts with `SAAS_ORCHESTRATION_BACKEND` unset
- **THEN** the `mock` backend is used and no Nebius API calls are made

### Requirement: Job creation from allowlisted presets only
The Nebius backend SHALL build each submission exclusively from an owned custom
preparation/training specification bound to an eligible or accepted preparation fingerprint, plus a
server-generated safe identity. It SHALL NOT accept tenant-supplied images, commands, code,
environment variables, storage keys/URLs, hardware values, hyperparameters, or secret references,
and it SHALL NOT retain any public-catalog submission source. Custom preparation and
`custom-ppo-quick` options MUST use the configured immutable generic SB3 runtime, the appropriate
server-owned entrypoint, and an allowlisted `cpu-d3` preset. The backend SHALL validate the typed
custom invariant before creating a remote Nebius resource.

#### Scenario: Public catalog submission is refused
- **WHEN** any caller or residual code path attempts to submit a public catalog production job
  specification, gallery example, or Go1 MJX profile
- **THEN** no Nebius resource is created, because the backend exposes no public-catalog submission
  source

#### Scenario: Custom preparation derives from an eligible setup
- **WHEN** an owner prepares a V1-eligible setup
- **THEN** the backend derives the immutable SB3 image, preparation mode, input prefix/fingerprint,
  `cpu-d3` platform/preset, timeout, and secret selectors from the typed server-owned preparation
  specification

#### Scenario: Custom training derives from accepted preparation
- **WHEN** an owner starts `custom-ppo-quick` for a current accepted fingerprint
- **THEN** the backend derives the immutable SB3 image, training mode, accepted input snapshot, fixed
  PPO profile, `cpu-d3` platform/preset, bounds, timeout, and secret selectors entirely server-side

#### Scenario: Missing or stale custom fingerprint is refused
- **WHEN** a custom training request lacks a current owned accepted preparation fingerprint
- **THEN** validation fails before a SaaS Job or Nebius resource is created

#### Scenario: Unsafe run or preparation identity is refused
- **WHEN** the backend builds a submission whose server identity does not match the safe configured
  pattern
- **THEN** the backend refuses submission and records a sanitized failure without reading a
  caller-selected prefix

#### Scenario: Submission derives from the matching typed specification
- **WHEN** any allowlisted preparation or custom-training workload is submitted
- **THEN** image, command/mode, configuration, platform, preset, timeout, disk, input/output
  prefixes, and bounds come entirely from its typed server-owned specification

#### Scenario: Custom SB3 spec runs on right-sized CPU hardware
- **WHEN** the backend builds a custom preparation or training submission
- **THEN** it uses the configured immutable generic SB3 runtime on the typed specification's
  allowlisted `cpu-d3` shape and never substitutes H100 or a tenant-selected backend

#### Scenario: Required immutable image configuration is missing
- **WHEN** the Nebius backend starts with custom robot training enabled but no generic SB3
  digest/profile configuration
- **THEN** settings validation fails before readiness and no affected job can be submitted

### Requirement: Preparation reconciliation is durable and artifact-gated
The Nebius adapter SHALL persist each preparation's returned `aijob-*` identity, poll non-terminal attempts across SaaS restarts, map provider state to sanitized preparation phases, and accept an attempt only after the required report is readable, valid, and fingerprint-matched. Submission, polling, execution, timeout, or finalization failure SHALL become terminal with bounded safe diagnostics and SHALL release the active quota reservation.

#### Scenario: Preparation remote identity is persisted
- **WHEN** the SDK creates a preparation job successfully
- **THEN** the returned remote identity is stored before the attempt is reported as running

#### Scenario: Remote success waits for report
- **WHEN** the preparation job succeeds but the report is not yet readable
- **THEN** the attempt remains in finalization and cannot enable Start training

#### Scenario: Backend restarts while polling
- **WHEN** the SaaS service starts with a non-terminal preparation and stored remote identity
- **THEN** reconciliation resumes without creating a duplicate remote job

### Requirement: Typed submission validators preserve the trust boundary
The orchestration layer SHALL implement distinct validation for custom preparation and custom
training specifications and SHALL have no generic pass-through job-spec path and no public MJX
submission path. For custom work it SHALL verify tenant ownership, eligibility/acceptance,
fingerprint, immutable input manifest, runtime digest, entrypoint mode, `cpu-d3` platform/preset,
timeout, and output prefix before SDK creation.

#### Scenario: Typed fields are mixed
- **WHEN** a custom preparation specification contains an MJX/H100 training field or a training
  specification contains a preparation input prefix
- **THEN** the backend rejects the internally inconsistent specification before remote creation

#### Scenario: Tenant field reaches SDK builder
- **WHEN** an untrusted request field is accidentally propagated toward the Nebius submission builder
- **THEN** the typed validator rejects it and tests demonstrate that it is not emitted to the SDK
  request

#### Scenario: No public submission validator remains
- **WHEN** the orchestration layer's submission validators are enumerated
- **THEN** only custom preparation and custom training validators exist, and no code path can build
  a public gallery submission

### Requirement: Nebius job ID persistence

The system SHALL store the Nebius-returned `aijob-*` resource ID on the job record at submission time so status polling and cancellation can address the remote job.

#### Scenario: Job record carries the Nebius ID

- **WHEN** the SDK's `create()` call returns successfully
- **THEN** the job record is updated with the `aijob-*` ID before any status is reported to the tenant

### Requirement: Status polling drives the tenant lifecycle
The Nebius backend SHALL reconcile active Nebius jobs onto the tenant lifecycle across process restarts. Remote training success SHALL transition the tenant job into finalization rather than directly to `completed`; `completed` SHALL be persisted only after the required report, metrics, artifact manifest, and declared media outputs are readable from object storage. Polling and finalization checks SHALL use bounded retry and timeout policies, persist phase and last-update information, and stop only at `completed` or `failed`.

#### Scenario: Running job is reflected to the tenant
- **WHEN** the Nebius job is executing
- **THEN** `GET /jobs/{job_id}` returns a non-terminal lifecycle status derived from the latest reconciliation

#### Scenario: Remote success waits for finalized artifacts
- **WHEN** the Nebius job succeeds but required finalization outputs are not yet available
- **THEN** the tenant job remains in a non-terminal finalization lifecycle state and the artifact API reports its structured readiness state

#### Scenario: Finalized run becomes completed
- **WHEN** all required report and media outputs are readable and valid
- **THEN** the artifact manifest is cached durably, the job becomes `completed`, and reconciliation stops

#### Scenario: Active jobs resume after SaaS restart
- **WHEN** the SaaS process starts with non-terminal jobs persisted in SQLite
- **THEN** it resumes reconciliation from their stored remote job identities without creating duplicate Nebius jobs

#### Scenario: Stale job fails with a bounded reason
- **WHEN** a job makes no acceptable progress beyond its configured deadline or required artifacts never finalize before timeout
- **THEN** it becomes `failed` with a sanitized failure phase and reason instead of remaining indefinitely in `starting` or loading results

#### Scenario: Terminal states end polling
- **WHEN** reconciliation persists artifact-gated `completed` or a terminal `failed` state
- **THEN** the backend stops polling and finalization checks for that job

### Requirement: Launch failure handling
If submission, polling, training, finalization, or artifact validation fails terminally, the system SHALL mark the job `failed` with a sanitized error summary and failure phase. It SHALL NOT leak credentials, raw provider responses, stack traces, tenant identifiers, or secret selectors to the tenant. The job API SHALL retain the remote job identity and last successful phase when available for operator diagnosis.

#### Scenario: Submission failure marks the job failed
- **WHEN** Nebius job creation raises a terminal error
- **THEN** the job status becomes `failed`, the stored failure phase is `submission`, and the public summary excludes secrets

#### Scenario: Finalization failure is distinguishable
- **WHEN** remote training succeeds but finalization fails terminally
- **THEN** the job status becomes `failed` with phase `finalization`, retaining its remote job identity and a sanitized tenant-visible reason

### Requirement: Showcase reads never reach the submission layer
The orchestration backend SHALL expose read-only artifact capability to the public showcase — manifest
reading, validation, and short-lived presigned URL issuance for a server-pinned run prefix — and
SHALL NOT expose job creation, launch, resume, or status-polling capability to any showcase route.

#### Scenario: Showcase requests a manifest
- **WHEN** the showcase resolves a pinned curated run
- **THEN** it uses only the backend's artifact reader against the reconstructed server-owned prefix

#### Scenario: Showcase path is traced to submission
- **WHEN** the call graph from any showcase route is examined
- **THEN** it reaches no launch, submit, or remote-resource-creating function

