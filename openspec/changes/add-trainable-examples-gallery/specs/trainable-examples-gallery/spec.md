## ADDED Requirements

### Requirement: Exact trainable examples gallery
The system SHALL expose exactly seven public gallery examples with stable IDs:
`go1-walker`, `ant-explorer`, `halfcheetah-sprint`, `hopper-balance`, `walker2d-stride`,
`humanoid-walk`, and `reacher-target`. Each entry SHALL include a label, concise task and
environment description, local avatar, expected result, backend and hardware labels, one
recommended bounded configuration, observed duration/cost guidance, success criteria, and a
server-owned production job-spec reference.

#### Scenario: User requests the gallery
- **WHEN** an authenticated client requests the public training catalog
- **THEN** it receives the seven examples in the documented order with complete display and
  executable metadata and no additional gallery card

#### Scenario: Existing Go1 sizes do not multiply cards
- **WHEN** the Go1 example exposes backward-compatible Standard and Quality workload sizes
- **THEN** the gallery still contains one `go1-walker` card and marks one bounded profile as its
  recommendation

### Requirement: Executability-gated publication
A gallery entry SHALL be returned or accepted only when its exact revision resolves to an
immutable runtime image, training configuration, allowlisted compute shape, timeout, evaluation
and render contract, required artifact contract, and recorded acceptance result. A direct request
for an unknown, hidden, or incomplete entry SHALL be rejected before a local job record or remote
resource is created.

#### Scenario: Fully accepted entry is published
- **WHEN** an entry has complete job-spec metadata and passing acceptance evidence for its current
  image and configuration revision
- **THEN** it is visible and can be submitted using its stable gallery ID

#### Scenario: Incomplete entry is hidden and rejected
- **WHEN** any required runtime, evaluation, artifact, compute, timeout, or acceptance field is
  missing or stale
- **THEN** the entry is omitted from the catalog and direct submission returns 422 without creating
  a SaaS or Nebius job

### Requirement: Server-resolved gallery submission
Submitting a gallery example SHALL send its stable example ID and only optional fields explicitly
allowlisted by that entry. The server SHALL derive the environment, algorithm, image, command,
compute shape, timeout, secret selectors, artifact prefix, and recommended defaults from the
catalog and persist the example ID plus the fully resolved configuration. Unknown fields and
out-of-range values SHALL return field-level 422 errors.

#### Scenario: Recommended example is submitted
- **WHEN** a tenant submits `hopper-balance` without optional overrides
- **THEN** the server creates a queued job using the exact recommended Hopper configuration and
  records `gallery_example_id: hopper-balance`

#### Scenario: Unsafe customization is attempted
- **WHEN** a client supplies an image, command, environment variable, arbitrary algorithm, or field
  outside the selected entry's declared bounds
- **THEN** the server returns 422 before creating any local or remote resource

#### Scenario: Historical job has no example identity
- **WHEN** the UI reads a pre-gallery job whose `gallery_example_id` is null
- **THEN** the API and UI continue to use its resolved environment/profile without inventing a
  gallery association

### Requirement: Honest measured guidance
Every visible example SHALL show observed end-to-end duration and cost guidance tied to the exact
accepted job-spec and immutable image revision. The UI SHALL distinguish observed ranges from live
run progress and SHALL NOT present an unmeasured estimate as a verified value.

#### Scenario: Accepted measurement is shown
- **WHEN** a gallery card is rendered from current acceptance evidence
- **THEN** its duration/cost guidance identifies the measured range and accepted revision

#### Scenario: Measurement becomes stale
- **WHEN** an entry's image, compute shape, or recommended workload changes after measurement
- **THEN** the entry is not publicly trainable until current acceptance evidence is recorded

### Requirement: Original accessible avatars
Each gallery example SHALL use an original, repository-owned, same-origin SVG avatar with a stable
aspect ratio and meaningful accessible label. Rendering the gallery SHALL make no third-party image
request.

#### Scenario: Gallery assets load
- **WHEN** the gallery is opened on mobile or desktop
- **THEN** all seven avatars render from local application assets without layout shift or an
  external network dependency

#### Scenario: Assistive technology reads a card
- **WHEN** a screen-reader user focuses an example card
- **THEN** the example name and task are available without relying on the avatar's appearance

### Requirement: Bring Your Robot remains isolated
Validated custom robots and environment drafts SHALL remain in the Bring Your Robot beta and SHALL
NOT appear as trainable gallery entries or be accepted by `POST /jobs`. Completing model or setup
validation SHALL NOT schedule a hidden GPU validation or automatically change the custom asset to
trainable.

#### Scenario: Validated custom setup exists
- **WHEN** a tenant has a `Validated setup` in My Robots and opens the training gallery
- **THEN** the setup is absent from the seven trainable examples and has no active Start Training
  action

#### Scenario: Validation completes without a training transition
- **WHEN** a tenant saves a valid custom robot setup
- **THEN** the setup remains validation-only until a separate accepted custom adapter capability
  exists, and no local or remote training job is created
