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

The Nebius backend SHALL build each job submission exclusively from the catalog-resolved preset configuration and the server-generated job ID. It SHALL NOT accept tenant-supplied images, commands, environment IDs, or code, and SHALL apply the preset's platform, timeout, and step limits to the submission. Each submission SHALL use the runtime image and compute shape (platform and preset) declared by the catalog job spec for the run's environment/algorithm combination: SB3-backed specs use the configured SB3 runtime image, and MJX-backed specs use the configured MJX runtime image. The backend's settings contract SHALL require both runtime image references at startup and SHALL fail readiness when either is missing.

#### Scenario: Submission derives from the preset catalog

- **WHEN** a tenant posts a job with an allowlisted preset
- **THEN** the backend submits a Serverless AI job whose image, container command, platform/preset, timeout, and limits come from the server-side catalog, parameterized only by the generated run ID and optional safe seed override

#### Scenario: MJX spec runs on the MJX runtime image

- **WHEN** the backend builds the submission for an MJX-backed job spec (e.g. `go1`/`ppo-mjx`)
- **THEN** the submission's image is the configured MJX runtime image and its platform/preset are the shape declared by that job spec

#### Scenario: SB3 spec runs on the SB3 runtime image and right-sized hardware

- **WHEN** the backend builds the submission for an SB3-backed job spec
- **THEN** the submission's image is the configured SB3 runtime image and its platform/preset are the SB3 spec's declared shape, which is not required to match the MJX shape

#### Scenario: Missing MJX image configuration fails startup

- **WHEN** the nebius backend is selected but the MJX runtime image variable is unset
- **THEN** settings validation fails at startup and the pod does not become ready, and no job submission is attempted

#### Scenario: Unsafe run IDs are refused

- **WHEN** the backend builds a submission whose run ID does not match the safe pattern `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`
- **THEN** the backend refuses to submit and the job is marked failed

### Requirement: Nebius job ID persistence

The system SHALL store the Nebius-returned `aijob-*` resource ID on the job record at submission time so status polling and cancellation can address the remote job.

#### Scenario: Job record carries the Nebius ID

- **WHEN** the SDK's `create()` call returns successfully
- **THEN** the job record is updated with the `aijob-*` ID before any status is reported to the tenant

### Requirement: Status polling drives the tenant lifecycle

The Nebius backend SHALL poll `JobService.get()` for each active job and map Nebius job states onto the tenant-visible lifecycle (`queued`, `starting`, `training`, `rendering`, `evaluating`, `completed`, `failed` — the same order as the data plane's canonical run lifecycle). Polling SHALL stop once a job reaches a terminal state.

#### Scenario: Running job is reflected to the tenant

- **WHEN** the Nebius job is executing
- **THEN** `GET /jobs/{job_id}` returns a non-terminal lifecycle status derived from the latest poll

#### Scenario: Terminal states end polling

- **WHEN** the Nebius job succeeds or fails
- **THEN** the job record is set to `completed` or `failed` respectively and the backend stops polling that job

### Requirement: Launch failure handling

If the Serverless AI job submission fails (SDK error, permission error, quota), the system SHALL mark the job `failed` with an error summary, SHALL NOT leak credentials or raw stack traces to the tenant, and SHALL report the failure on subsequent status requests.

#### Scenario: Submission failure marks the job failed

- **WHEN** `JobServiceClient.create()` raises an error
- **THEN** the job status becomes `failed`, the stored error summary excludes secrets, and `GET /jobs/{job_id}` reports the failure
