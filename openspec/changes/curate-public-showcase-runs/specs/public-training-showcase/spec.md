## MODIFIED Requirements

### Requirement: Unauthenticated showcase catalog
The system SHALL expose `GET /showcase` without any session, bearer token, or cookie. The response
SHALL list the published showcase entries in the documented gallery order, each carrying its stable
example ID, label, task, description, local avatar, expected result, backend and hardware labels,
the sanitized resolved configuration that the pinned run actually executed, measured duration and
cost with rate date, success criterion, primary metric, selected checkpoint, progress summary, and
acceptance revision. Evidence fields SHALL be derived from the validated pinned run rather than
current catalog defaults. The response SHALL contain no tenant identity, email, job ID, bucket name,
object key, credential, secret selector, or presigned URL.

#### Scenario: Anonymous visitor lists the showcase
- **WHEN** a client requests `GET /showcase` with no `Authorization` header
- **THEN** the API returns 200 with the published entries and their display and measured evidence
  metadata

#### Scenario: Catalog defaults differ from pinned evidence
- **WHEN** current server defaults differ from the configuration, hardware, rate, or runtime recorded
  by a pinned run
- **THEN** the response shows the sanitized pinned-run values and does not relabel the historical run

#### Scenario: Showcase leaks no tenant or storage identity
- **WHEN** any showcase response is inspected
- **THEN** it contains no tenant email, job ID, bucket name, object key, credential, secret selector,
  or unallowlisted resolved-configuration field

#### Scenario: Session header is neither required nor honoured
- **WHEN** a client sends `GET /showcase` with an expired, forged, or another tenant's bearer token
- **THEN** the API returns the same public response and performs no session-scoped lookup

### Requirement: Evidence-gated publication
A showcase entry SHALL be published only when its pinned run's manifest is readable and valid,
every required artifact exists in-prefix with safe identity and integrity metadata, its canonical
runtime environment and resolved example identity match the server-owned declaration, its
evaluation uses a recognized schema and records task success as true, and its measured provenance
and progress record validate. An entry that fails any check SHALL be omitted from `GET /showcase`
and SHALL return 404 on direct request. Omission SHALL be a normal, non-error state for the service
as a whole.

#### Scenario: Curated run is complete and successful
- **WHEN** a pinned run's manifest, provenance, deterministic evaluation, selected checkpoint,
  required progress/media, and task-success result all validate
- **THEN** the entry is published with its measured evidence and playable media

#### Scenario: Runtime uses canonical environment identity
- **WHEN** a run records an allowlisted canonical environment such as `Ant-v5` or
  `Go1JoystickFlatTerrain` for the corresponding friendly example ID, or
  `G1ForwardRoughTerrain` for the G1 Walk Forward recovery card
- **THEN** the identity gate accepts the exact server-declared mapping without weakening it to a
  caller-controlled or fuzzy match

#### Scenario: Curated run completed below threshold
- **WHEN** artifacts are complete but normalized `success.met` is false or a locomotion episode
  violates its configured all-episode gate
- **THEN** the entry remains unpublished and cannot be described as a verified example

#### Scenario: Curated run does not exist yet
- **WHEN** an example's pinned run has produced no manifest because curation has not completed
- **THEN** the entry is absent from the catalog, a direct request returns 404, and `GET /showcase`
  still returns 200 for the remaining entries

#### Scenario: Every entry is unpublished
- **WHEN** no pinned run yet validates
- **THEN** `GET /showcase` returns 200 with an empty entry list rather than a 5xx or an error page

#### Scenario: Curated manifest or evaluation schema is invalid
- **WHEN** a pinned run references a missing, unsafe, out-of-prefix, digest-mismatched, ambiguous, or
  unrecognized evidence value
- **THEN** the entry is withheld and a sanitized validation failure is recorded without exposing the
  value

### Requirement: Public showcase result detail
The system SHALL expose `GET /showcase/{example_id}` without a session, returning the entry's
identity, sanitized resolved configuration that actually ran, structured final evaluation metrics,
successful evaluation state separate from infrastructure completion, selected checkpoint identity,
runtime versions, measured runtime/cost, evaluated progress stages with exact steps and media IDs,
and publicly available artifacts with opaque identifiers, human-readable names, kinds, content
types, sizes, and public access URLs. Nested metric objects SHALL be returned as structured data.

#### Scenario: Anonymous visitor opens an example
- **WHEN** a client requests a published example ID with no credentials
- **THEN** the API returns its measured configuration, final and progress metrics, selected
  checkpoint, evaluation success, and artifact list with public access URLs

#### Scenario: Visitor compares training stages
- **WHEN** a published example has initial, intermediate, and selected progress evidence
- **THEN** detail identifies the exact checkpoint step and media for every stage and labels any
  measured regression honestly

#### Scenario: Unknown or unpublished example is requested
- **WHEN** a client requests an example ID that is unknown, hidden, below threshold, or failing any
  evidence gate
- **THEN** the API returns 404 without revealing which of those cases applies

#### Scenario: Diagnostic run is hardcoded accidentally
- **WHEN** a pinned run finished artifact production but did not meet its task threshold
- **THEN** neither catalog nor detail publishes it, even though its infrastructure status is
  completed
