## MODIFIED Requirements

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
