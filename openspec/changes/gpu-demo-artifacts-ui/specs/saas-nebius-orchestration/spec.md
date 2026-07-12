## MODIFIED Requirements

### Requirement: Job creation from allowlisted presets only
The Nebius backend SHALL build each job submission exclusively from a catalog-resolved production job specification and the server-generated job ID. It SHALL NOT accept tenant-supplied images, commands, code, environment variables, or secret references. Each public production option MUST use the configured immutable MJX runtime image and an allowlisted H100 GPU platform/preset; the backend SHALL validate this invariant before creating the local job record or remote Nebius resource.

#### Scenario: GPU profile derives from the production catalog
- **WHEN** a tenant submits Quick, Standard, or Quality
- **THEN** the backend derives the immutable MJX image, Go1 config, H100 platform/preset, bounded workload settings, timeout, and secret selectors entirely from the server-owned job specification

#### Scenario: Non-GPU or missing job spec is refused before creation
- **WHEN** a request resolves to an SB3, non-GPU, or missing production job specification
- **THEN** validation returns 422 before a SaaS job record or Nebius job is created

#### Scenario: Unsafe run IDs are refused
- **WHEN** the backend builds a submission whose run ID does not match the safe pattern `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`
- **THEN** the backend refuses to submit and the job is marked failed

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

### Requirement: Launch failure handling
If submission, polling, training, finalization, or artifact validation fails terminally, the system SHALL mark the job `failed` with a sanitized error summary and failure phase. It SHALL NOT leak credentials, raw provider responses, stack traces, tenant identifiers, or secret selectors to the tenant. The job API SHALL retain the remote job identity and last successful phase when available for operator diagnosis.

#### Scenario: Submission failure marks the job failed
- **WHEN** Nebius job creation raises a terminal error
- **THEN** the job status becomes `failed`, the stored failure phase is `submission`, and the public summary excludes secrets

#### Scenario: Finalization failure is distinguishable
- **WHEN** remote training succeeds but finalization fails terminally
- **THEN** the job status becomes `failed` with phase `finalization`, retaining its remote job identity and a sanitized tenant-visible reason

