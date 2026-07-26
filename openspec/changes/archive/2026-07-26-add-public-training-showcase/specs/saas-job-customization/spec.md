## MODIFIED Requirements

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

### Requirement: Custom job submission
The system SHALL create training jobs only from an owner starting their own accepted custom robot
setup via `POST /robot-setups/{setup_id}/training-jobs`, which accepts the setup identity plus
idempotency metadata and nothing else. `POST /jobs` SHALL NOT accept a gallery example ID, gallery
profile ID, preset, environment, algorithm, or parameter override. The system SHALL validate every
field against server-owned allowlists; unknown fields, identities, or out-of-range values SHALL be
rejected with 422 and a field-level error. Arbitrary code, images, commands, environment variables,
secret selectors, and compute choices SHALL NOT be accepted on any route.

#### Scenario: Valid custom job accepted
- **WHEN** an owner starts a setup whose latest preparation fingerprint is current and accepted
- **THEN** the system responds 201 with a queued job recording the setup identity and full resolved
  server-owned configuration

#### Scenario: Gallery submission is refused
- **WHEN** a client posts a gallery example ID, gallery profile ID, or Go1 preset ID to `/jobs`
- **THEN** the system rejects the request and creates neither a SaaS job record nor a Nebius resource

#### Scenario: Unknown field rejected
- **WHEN** a custom start submission supplies a backend, algorithm, hardware, image, command, PPO,
  task, scene, or object override
- **THEN** the system responds 422 naming the offending field and no job is created

## REMOVED Requirements

### Requirement: Backward-compatible presets
**Reason**: The three named Go1 workload profiles existed solely as submittable shortcuts into the
public MJX catalog. With gallery training removed, no route accepts a profile ID, so a requirement
guaranteeing their continued submittability guarantees a path that no longer exists.
**Migration**: The Go1 workload definitions survive as the recorded resolved configuration of the
`go1-walker` pinned curated run and are displayed by the showcase as historical evidence. Existing
jobs created from `go1-mjx-quick`, `go1-mjx-standard`, or `go1-mjx-quality` keep their persisted
`preset` value and remain readable in their owner's dashboard; a new submission of any of these IDs
returns 422.
