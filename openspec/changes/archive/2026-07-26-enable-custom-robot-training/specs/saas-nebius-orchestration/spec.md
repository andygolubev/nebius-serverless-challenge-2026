## MODIFIED Requirements

### Requirement: Job creation from allowlisted presets only
The Nebius backend SHALL build each submission exclusively from one of two typed server-resolved sources plus a server-generated safe identity: (1) a public catalog production job specification or (2) an owned custom preparation/training specification bound to an eligible or accepted preparation fingerprint. It SHALL NOT accept tenant-supplied images, commands, code, environment variables, storage keys/URLs, hardware values, hyperparameters, or secret references. Public catalog production options MUST continue to use the configured immutable MJX runtime and allowlisted H100 platform/preset. Custom preparation and `custom-ppo-quick` options MUST use the configured immutable generic SB3 runtime, the appropriate server-owned entrypoint, and an allowlisted `cpu-d3` preset. The backend SHALL validate the selected typed invariant before creating a remote Nebius resource.

#### Scenario: GPU profile derives from the production catalog
- **WHEN** a tenant submits Quick, Standard, or Quality from the public catalog
- **THEN** the backend derives the immutable MJX image, gallery environment config, H100 platform/preset, bounded workload settings, timeout, and secret selectors entirely from the server-owned public job specification

#### Scenario: Unsupported public option is refused before creation
- **WHEN** a public catalog request resolves to an unlisted SB3, non-GPU, missing, or malformed production job specification
- **THEN** validation returns 422 before a SaaS job record or Nebius resource is created

#### Scenario: Custom preparation derives from an eligible setup
- **WHEN** an owner prepares a V1-eligible setup
- **THEN** the backend derives the immutable SB3 image, preparation mode, input prefix/fingerprint, `cpu-d3` platform/preset, timeout, and secret selectors from the typed server-owned preparation specification

#### Scenario: Custom training derives from accepted preparation
- **WHEN** an owner starts `custom-ppo-quick` for a current accepted fingerprint
- **THEN** the backend derives the immutable SB3 image, training mode, accepted input snapshot, fixed PPO profile, `cpu-d3` platform/preset, bounds, timeout, and secret selectors entirely server-side

#### Scenario: Missing or stale custom fingerprint is refused
- **WHEN** a custom training request lacks a current owned accepted preparation fingerprint
- **THEN** validation fails before a SaaS Job or Nebius resource is created

#### Scenario: Unsafe run or preparation identity is refused
- **WHEN** the backend builds a submission whose server identity does not match the safe configured pattern
- **THEN** the backend refuses submission and records a sanitized failure without reading a caller-selected prefix

#### Scenario: Submission derives from the matching typed specification
- **WHEN** any allowlisted public, preparation, or custom-training workload is submitted
- **THEN** image, command/mode, configuration, platform, preset, timeout, disk, input/output prefixes, and bounds come entirely from its typed server-owned specification

#### Scenario: MJX spec runs on the MJX runtime image
- **WHEN** the backend builds any public gallery production submission
- **THEN** it uses the configured immutable MJX runtime image on the profile's allowlisted H100 shape

#### Scenario: Custom SB3 spec runs on right-sized CPU hardware
- **WHEN** the backend builds a custom preparation or training submission
- **THEN** it uses the configured immutable generic SB3 runtime on the typed specification's allowlisted `cpu-d3` shape and never substitutes H100 or a tenant-selected backend

#### Scenario: Required immutable image configuration is missing
- **WHEN** the Nebius backend starts with public production enabled but no MJX digest, or with custom robot training enabled but no generic SB3 digest/profile configuration
- **THEN** settings validation fails before readiness and no affected job can be submitted

## ADDED Requirements

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
The orchestration layer SHALL implement distinct validation for public MJX, custom preparation, and custom training specifications and SHALL have no generic pass-through job-spec path. For custom work it SHALL verify tenant ownership, eligibility/acceptance, fingerprint, immutable input manifest, runtime digest, entrypoint mode, `cpu-d3` platform/preset, timeout, and output prefix before SDK creation.

#### Scenario: Typed fields are mixed
- **WHEN** a custom preparation specification contains an MJX/H100 training field or a public job contains a custom input prefix
- **THEN** the backend rejects the internally inconsistent specification before remote creation

#### Scenario: Tenant field reaches SDK builder
- **WHEN** an untrusted request field is accidentally propagated toward the Nebius submission builder
- **THEN** the typed validator rejects it and tests demonstrate that it is not emitted to the SDK request

