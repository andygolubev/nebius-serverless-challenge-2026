# public-training-showcase Specification

## Purpose
TBD - created by archiving change add-public-training-showcase. Update Purpose after archive.
## Requirements
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

### Requirement: Server-pinned curated run per example
Each showcase entry SHALL bind exactly one gallery example ID to exactly one curated run identity
declared in server-owned source. The pinned run identity SHALL match the safe run-identity pattern
and SHALL resolve to a prefix beneath the server-owned artifact root. A client SHALL NOT be able to
supply, override, enumerate, or influence which run an example resolves to.

#### Scenario: Entry resolves its pinned run
- **WHEN** the showcase serves an example
- **THEN** it reads only the prefix reconstructed from that example's server-declared pinned run
  identity

#### Scenario: Client supplies a run identity
- **WHEN** a request carries a run ID, job ID, storage key, prefix, or tenant hint as a parameter,
  path segment, or header
- **THEN** the value is rejected or ignored and no caller-directed storage read occurs

#### Scenario: Pinned identity is unsafe
- **WHEN** a declared pinned run identity fails the safe-pattern or containment check at startup
- **THEN** the entry is not published and the failure is recorded without exposing the raw value

### Requirement: Evidence-gated publication
A showcase entry SHALL be published only when its pinned run's manifest is readable and valid,
every required artifact exists in-prefix with safe identity and integrity metadata, its canonical
runtime environment and resolved example identity match the server-owned declaration, its
evaluation uses a recognized schema and records task success as true, except for the one exact
operator-reviewed G1 verified-recording tuple, and its measured provenance and progress record
validate. An entry that fails any check SHALL be omitted from `GET /showcase`
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
- **THEN** the entry remains unpublished unless it is the exact operator-reviewed G1
  verified-recording tuple

#### Scenario: Exact G1 verified recording is published below threshold
- **WHEN** example `g1-rough-terrain` resolves to run
  `showcase-gallery-g1-20260801-16-g1-s0-rough`, its canonical joystick rough-terrain identity,
  immutable provenance, manifest, checksums, bundle, checkpoint, metrics, runtime/cost, and media all
  validate, and its recorded task success is false
- **THEN** the entry is published as a verified recorded run with `evaluation.success: false`, its
  actual 0/20 horizon result, and no pass/fail threshold badge; it is never represented as an
  accepted locomotion result

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

The public gallery and detail UI SHALL NOT render met-task-threshold or below-task-threshold badges.
The public detail SHALL NOT render the derived KPI metric grid. It SHALL retain the header/meta rail,
simulator-only note, compact success-criterion/primary-metric/observed-duration/observed-cost facts,
policy bundle, rollout media, evidence accordions, artifacts/configuration, and closing CTA. This
presentation rule SHALL NOT remove or rewrite evaluation data returned by the API, and SHALL NOT
remove the KPI grid from the authenticated owner job result.

#### Scenario: Anonymous visitor opens an example
- **WHEN** a client requests a published example ID with no credentials
- **THEN** the API returns its measured configuration, final and progress metrics, selected
  checkpoint, evaluation success, and artifact list with public access URLs

#### Scenario: Visitor compares training stages
- **WHEN** a published example has initial, intermediate, and selected progress evidence
- **THEN** detail identifies the exact checkpoint step and media for every stage and labels any
  measured regression honestly

#### Scenario: Public result omits threshold chrome and KPI cells
- **WHEN** a visitor opens the gallery or a published run detail
- **THEN** no met/below threshold badge or KPI cell grid is rendered, while the compact measured
  facts and structured evidence remain available

#### Scenario: Owner result keeps its KPI summary
- **WHEN** an authenticated owner opens a normal job result
- **THEN** its existing KPI grid remains available because the public showcase presentation change
  is scoped to `ShowcaseDetail`

#### Scenario: Unknown or unpublished example is requested
- **WHEN** a client requests an example ID that is unknown, hidden, below threshold, or failing any
  evidence gate
- **THEN** the API returns 404 without revealing which of those cases applies

#### Scenario: Diagnostic run is hardcoded accidentally
- **WHEN** a pinned run finished artifact production but did not meet its task threshold
- **THEN** neither catalog nor detail publishes it, even though its infrastructure status is
  completed, unless it matches the exact reviewed G1 verified-recording tuple

### Requirement: Session-free allowlisted artifact delivery
The system SHALL expose `GET /showcase/{example_id}/artifacts/{artifact_id}` without a session. Each
access SHALL resolve the example to its pinned run, resolve the opaque artifact identifier against
that run's cached validated manifest, and either stream the object with HTTP range support or
redirect to a short-lived presigned HTTPS URL. Callers SHALL NOT supply object keys, prefixes, or
content dispositions. The showcase artifact route SHALL NOT be capable of returning an object
belonging to any tenant-owned run, and the artifact bucket SHALL remain private.

#### Scenario: Anonymous visitor plays a rollout
- **WHEN** a visitor requests a published example's MP4 artifact
- **THEN** the response supports browser playback and byte-range seeking with `video/mp4` content
  type

#### Scenario: Artifact identifier is not in the manifest
- **WHEN** a caller supplies an artifact identifier absent from the pinned run's validated manifest
- **THEN** the API returns 404 and performs no storage read for the caller-supplied value

#### Scenario: Showcase route is aimed at a tenant run
- **WHEN** a caller substitutes a tenant job ID, tenant run ID, or traversing value for the example
  ID or artifact ID
- **THEN** the API returns 404, reads no tenant prefix, and reveals nothing about the tenant run's
  existence

#### Scenario: Presigned exposure is bounded
- **WHEN** the showcase issues a presigned URL
- **THEN** it is short-lived, scoped to exactly one validated in-prefix object, and grants no list,
  write, or sibling-object access

### Requirement: Showcase cannot start training
No showcase route SHALL create, queue, mutate, or schedule a local job record, remote compute
resource, preparation, or storage write, under any parameter, method, or header. Public showcase
responses SHALL NOT advertise a training action for a showcase entry.

#### Scenario: Visitor attempts to trigger training
- **WHEN** an anonymous or authenticated client sends any write method or training-shaped payload to
  a showcase route
- **THEN** the request is refused and neither a SaaS record nor a remote resource is created

#### Scenario: Authenticated user views the showcase
- **WHEN** a signed-in tenant opens a showcase entry
- **THEN** the response offers inspection and media only, with no start-training affordance for that
  entry

#### Scenario: Only custom training creates jobs
- **WHEN** the service's job-creating surface is enumerated
- **THEN** the sole path that creates a training job is an owner starting their own accepted custom
  robot setup

### Requirement: Bounded public exposure
Public showcase reads SHALL be safe to expose to unauthenticated traffic: responses SHALL be
derived from durably cached validated manifests rather than a per-request storage crawl, per-client
request rates SHALL be bounded, and a storage or upstream failure SHALL degrade to a sanitized
unavailable state rather than an unhandled 5xx or a leaked storage error.

#### Scenario: Repeated anonymous traffic
- **WHEN** many anonymous requests hit the showcase catalog
- **THEN** responses are served from the cached validated manifests without a per-request object
  listing per entry

#### Scenario: Storage is unavailable
- **WHEN** an artifact access or manifest refresh fails upstream
- **THEN** the API returns a sanitized unavailable response that exposes no bucket, key, or
  credential detail

#### Scenario: Abusive request rate
- **WHEN** a single client exceeds the configured public request budget
- **THEN** the API returns 429 and the showcase remains available to other clients

