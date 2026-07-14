## MODIFIED Requirements

### Requirement: Job creation from allowlisted presets only
The Nebius backend SHALL build each job submission exclusively from a catalog-resolved production
job specification and the server-generated job ID. It SHALL NOT accept tenant-supplied images,
commands, code, environment variables, compute shapes, or secret references. Go1 MJX/JAX jobs
MUST use the configured immutable MJX runtime and accepted H100 platform/preset. SB3 gallery jobs
MUST use the configured immutable SB3 runtime and their accepted CPU or cheapest validated L40S
shape and MUST NOT use H100. The backend SHALL validate these invariants before creating the local
job record or remote Nebius resource.

#### Scenario: Go1 profile derives from the production catalog
- **WHEN** a tenant submits Go1 Quick, Standard, or Quality
- **THEN** the backend derives the immutable MJX image, Go1 config, H100 platform/preset, bounded
  workload, timeout, and secret selectors entirely from the server-owned job specification

#### Scenario: SB3 example derives from the production catalog
- **WHEN** a tenant submits one of the six accepted SB3 gallery examples
- **THEN** the backend derives its immutable SB3 image, exact environment config, right-sized CPU or
  L40S shape, bounded workload, timeout, evaluation contract, and secret selectors entirely from
  the server-owned job specification

#### Scenario: Missing or unaccepted job spec is refused before creation
- **WHEN** a request resolves to a missing, incomplete, stale, or unaccepted production job
  specification
- **THEN** validation returns 422 before a SaaS job record or Nebius job is created

#### Scenario: Unsafe run IDs are refused
- **WHEN** the backend builds a submission whose run ID does not match the safe pattern
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`
- **THEN** the backend refuses to submit and the job is marked failed

#### Scenario: Submission derives from the gallery catalog
- **WHEN** a tenant submits an allowlisted gallery example
- **THEN** image, command, config, platform, preset, timeout, bounds, and artifact contract come
  entirely from its server-owned production job specification

#### Scenario: MJX spec runs on the MJX runtime image
- **WHEN** the backend builds the Go1 gallery submission
- **THEN** it uses the configured immutable MJX runtime on the profile's accepted H100 shape

#### Scenario: SB3 spec uses right-sized hardware
- **WHEN** the backend builds an SB3 gallery submission
- **THEN** it uses the configured immutable SB3 runtime on its accepted CPU or L40S shape and never
  requests H100

#### Scenario: Missing enabled runtime configuration fails startup
- **WHEN** the Nebius backend starts without the immutable MJX or SB3 runtime required by an enabled
  public entry
- **THEN** settings validation fails before readiness and no job can be submitted

