# trainable-examples-gallery Specification

## Purpose
Replace the free-form job composer with exactly seven server-owned, evidence-backed trainable
examples so every tenant submission resolves to a complete, accepted production job specification,
while keeping Bring Your Robot custom assets isolated from public training.
## Requirements
### Requirement: Exact trainable examples gallery
The system SHALL expose exactly seven public showcase examples with stable IDs:
`go1-walker`, `ant-explorer`, `halfcheetah-sprint`, `hopper-balance`, `walker2d-stride`,
`g1-rough-terrain`, and `reacher-target`. Each entry SHALL include a label, concise task and
environment description, local avatar, expected result, backend and hardware labels, the bounded
configuration that its curated run actually executed, observed duration/cost guidance, success
criteria, and a server-owned pinned curated run reference. No entry SHALL carry an executable
submission contract.

#### Scenario: User requests the gallery
- **WHEN** any visitor requests the public showcase catalog
- **THEN** it receives the published examples in the documented order with complete display and
  evidence metadata, no additional card, and no submission affordance

#### Scenario: Existing Go1 sizes do not multiply cards
- **WHEN** the Go1 example's curated run used one of the historical Standard or Quality workload
  sizes
- **THEN** the showcase still contains one `go1-walker` card and reports the single workload that
  its pinned run actually ran

### Requirement: Honest measured guidance
Every visible example SHALL show observed end-to-end duration and cost guidance tied to its exact
pinned curated run and the immutable image revision that run used. The UI SHALL present these as
recorded historical measurements of a completed run and SHALL NOT present an unmeasured estimate as
a verified value or imply a live run.

#### Scenario: Accepted measurement is shown
- **WHEN** a showcase card is rendered from its pinned run's recorded evidence
- **THEN** its duration/cost guidance identifies the measured value and the run's accepted revision

#### Scenario: Measurement becomes stale
- **WHEN** an entry's declared configuration, image, or compute shape no longer matches what its
  pinned run recorded
- **THEN** the entry is withheld from the public showcase until the declaration and the pinned run
  agree

### Requirement: Original accessible avatars
Each showcase example SHALL use an original, repository-owned, same-origin SVG avatar with a stable
aspect ratio and meaningful accessible label. Rendering the showcase SHALL make no third-party image
request, including for unauthenticated visitors.

#### Scenario: Gallery assets load
- **WHEN** the showcase is opened on mobile or desktop, signed in or not
- **THEN** all published avatars render from local application assets without layout shift or an
  external network dependency

#### Scenario: Assistive technology reads a card
- **WHEN** a screen-reader user focuses an example card
- **THEN** the example name and task are available without relying on the avatar's appearance

### Requirement: Server-selected training backend
Every showcase entry SHALL report exactly one SB3 or MJX backend — the one its pinned curated run
used. The UI SHALL display that backend as informational metadata about a historical run and SHALL
NOT provide any backend, algorithm, or compute selector.

#### Scenario: User reviews a card
- **WHEN** any visitor opens G1 Rough Terrain
- **THEN** the detail identifies MJX/JAX PPO and the hardware its curated run used, with no SB3
  toggle and no way to re-run it

#### Scenario: Client attempts backend override
- **WHEN** a client sends an algorithm, backend, or hardware value to a showcase route
- **THEN** the value is rejected or ignored and no SaaS job or remote resource is created

