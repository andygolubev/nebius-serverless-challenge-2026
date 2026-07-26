## MODIFIED Requirements

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

## ADDED Requirements

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
