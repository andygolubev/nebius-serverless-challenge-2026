# saas-job-customization Specification

## Purpose
Define what an authenticated tenant may cause to run: exactly one job-creating route, bound to the
tenant's own accepted custom robot setup, with every execution parameter owned by the server. The
public catalog is display metadata only, and no route accepts arbitrary code, images, commands, or
compute choices.

## Requirements
### Requirement: Training options catalog
The system SHALL expose `GET /training-options` as unauthenticated display metadata for the public
showcase, not as a submission catalog. It SHALL publish the showcase entries that pass their evidence
gate, describing for each the configuration its pinned curated run executed, its backend and hardware
labels, and its measured guidance. The response SHALL NOT advertise a submittable environment,
algorithm, preset, profile, or parameter contract, because no field of it is accepted by any
job-creating endpoint. Entries whose pinned run is missing or invalid SHALL NOT be returned.

#### Scenario: Catalog contains only published showcase evidence
- **WHEN** any client requests `/training-options`
- **THEN** every returned entry corresponds to a validated curated run and carries display metadata
  only

#### Scenario: Catalog advertises no submission contract
- **WHEN** the response is inspected for submittable fields
- **THEN** it declares no environment/algorithm submission combination, preset ID, profile ID, or
  overridable parameter contract

#### Scenario: Entry without evidence is hidden
- **WHEN** an example's pinned curated run has no valid manifest
- **THEN** it is absent from `/training-options` and no route accepts its example ID for training

### Requirement: Custom job submission is the only job-creating route
The system SHALL create training jobs only from an owner starting their own accepted custom robot
setup via `POST /robot-setups/{setup_id}/training-jobs`, which accepts the setup identity plus
idempotency metadata and nothing else. `POST /jobs` SHALL be retired: it SHALL create neither a SaaS
job record nor a remote resource under any payload, and SHALL answer an old client with a stable
`410 Gone` naming the supported route rather than a 404. The system SHALL validate every field
against server-owned allowlists; unknown fields, identities, or out-of-range values SHALL be rejected
with 422 and a field-level error. Arbitrary code, images, commands, environment variables, secret
selectors, and compute choices SHALL NOT be accepted on any route.

#### Scenario: Valid custom job accepted
- **WHEN** an owner starts a setup whose latest preparation fingerprint is current and accepted
- **THEN** the system responds 201 with a queued job recording the setup identity and full resolved
  server-owned configuration

#### Scenario: Gallery submission is refused
- **WHEN** a client posts a gallery example ID, gallery profile ID, preset, environment, algorithm,
  or parameter override to `/jobs`
- **THEN** the system responds 410 with guidance toward the setup-bound route and creates neither a
  SaaS job record nor a Nebius resource

#### Scenario: Unknown field rejected
- **WHEN** a custom start submission supplies a backend, algorithm, hardware, image, command, PPO,
  task, scene, or object override
- **THEN** the system responds 422 naming the offending field and no job is created

### Requirement: Resolved configuration on the job record
The system SHALL persist and return the fully resolved server-owned configuration on the job record
so the owner can see exactly what ran, including the fixed training profile and its version, the
robot/setup/preparation provenance, and the immutable runtime image reference. Nothing in the
resolved configuration SHALL originate from the request.

#### Scenario: Job shows resolved configuration
- **WHEN** an owner fetches a job created from one of their accepted setups
- **THEN** the response includes the resolved task, scene, adapter/reward versions, fixed PPO profile
  and its version, compute shape, and immutable runtime reference

#### Scenario: Resolved configuration is reproducible
- **WHEN** two jobs are started from the same accepted fingerprint and runtime digest
- **THEN** their resolved server-owned configurations are identical

### Requirement: Tenant isolation of jobs and results
The system SHALL scope every job and its artifacts to the tenant that created it, deriving that
tenant from the session's verified email rather than from any caller-supplied value. One tenant SHALL
NOT be able to read, act on, or infer the existence of another tenant's jobs.

#### Scenario: Tenant sees only own jobs
- **WHEN** a tenant lists jobs
- **THEN** the response contains only that tenant's jobs

#### Scenario: Cross-tenant job is indistinguishable from a missing one
- **WHEN** a tenant requests a job, artifact, or artifact download belonging to another tenant
- **THEN** the API returns 404 without revealing whether the resource exists

### Requirement: Pluggable orchestration keeps the tenant contract stable
Job orchestration SHALL sit behind an interface with at least a `mock` implementation that drives the
full lifecycle and produces placeholder artifacts with no Nebius credentials or accelerator, so the
whole tenant surface is exercisable locally. Switching the backend by configuration SHALL NOT change
any tenant-facing request or response shape.

#### Scenario: Mock backend drives the full lifecycle
- **WHEN** the app is configured with the mock orchestration backend and an owner starts an accepted
  setup
- **THEN** the job progresses through the full status lifecycle and produces placeholder artifacts
  without any Nebius call

#### Scenario: Backend is selected by configuration
- **WHEN** the orchestration backend is switched by configuration
- **THEN** the tenant-facing API request and response shapes remain unchanged
