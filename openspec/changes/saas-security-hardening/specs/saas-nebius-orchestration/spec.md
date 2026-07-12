# saas-nebius-orchestration Delta

## MODIFIED Requirements

### Requirement: Job creation from allowlisted presets only

The Nebius backend SHALL build each job submission exclusively from the catalog-resolved preset configuration and the server-generated job ID. It SHALL NOT accept tenant-supplied images, commands, environment IDs, or code, and SHALL apply the preset's platform, timeout, and step limits to the submission. The container command SHALL be passed to the SDK as a discrete argument list, never as a single space-joined string, so that no argument value can be split or injected into an adjacent argument. Job submission SHALL rely on the scoped service-account credential (see `saas-cloud-least-privilege`), not an administrative role.

#### Scenario: Submission derives from the preset catalog

- **WHEN** a tenant posts a job with an allowlisted preset
- **THEN** the backend submits a Serverless AI job whose image, container command, platform/preset, timeout, and limits come from the server-side catalog, parameterized only by the generated run ID and optional safe seed override

#### Scenario: Unsafe run IDs are refused

- **WHEN** the backend builds a submission whose run ID does not match the safe pattern `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`
- **THEN** the backend refuses to submit and the job is marked failed

#### Scenario: Container arguments are passed as a list

- **WHEN** the SDK client builds the Serverless AI job request from a submission
- **THEN** the container arguments are supplied as a discrete list of argument strings, not a single space-joined string
