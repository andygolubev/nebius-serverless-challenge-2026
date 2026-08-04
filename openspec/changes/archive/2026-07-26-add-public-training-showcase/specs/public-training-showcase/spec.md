## ADDED Requirements

### Requirement: Unauthenticated showcase catalog
The system SHALL expose `GET /showcase` without any session, bearer token, or cookie. The response
SHALL list the published showcase entries in the documented gallery order, each carrying its stable
example ID, label, task, description, local avatar, expected result, backend and hardware labels,
the resolved configuration that actually ran, observed duration and cost, success criterion, primary
metric, and the acceptance revision of its pinned run. The response SHALL contain no tenant
identity, email, job ID, bucket name, object key, credential, or presigned URL.

#### Scenario: Anonymous visitor lists the showcase
- **WHEN** a client requests `GET /showcase` with no `Authorization` header
- **THEN** the API returns 200 with the published entries and their display and evidence metadata

#### Scenario: Showcase leaks no tenant or storage identity
- **WHEN** any showcase response is inspected
- **THEN** it contains no tenant email, job ID, bucket name, object key, or credential

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
A showcase entry SHALL be published only when its pinned run's manifest is readable and valid, every
required artifact it advertises exists in-prefix with a safe identifier, name, kind, content type,
and integrity metadata, and its recorded evaluation state is present. An entry that fails any check
SHALL be omitted from `GET /showcase` and SHALL return 404 on direct request. Omission SHALL be a
normal, non-error state for the service as a whole.

#### Scenario: Curated run is complete
- **WHEN** a pinned run's manifest, metrics, and required media validate
- **THEN** the entry is published with its measured evidence and playable media

#### Scenario: Curated run does not exist yet
- **WHEN** an example's pinned run has produced no manifest because the curated training has not
  been performed
- **THEN** the entry is absent from the catalog, a direct request returns 404, and `GET /showcase`
  still returns 200 for the remaining entries

#### Scenario: Every entry is unpublished
- **WHEN** no pinned run yet validates
- **THEN** `GET /showcase` returns 200 with an empty entry list rather than a 5xx or an error page

#### Scenario: Curated manifest is invalid
- **WHEN** a pinned run's manifest references a missing, unsafe, out-of-prefix, or digest-mismatched
  object
- **THEN** the entry is withheld and a sanitized validation failure is recorded without exposing the
  reference

### Requirement: Public showcase result detail
The system SHALL expose `GET /showcase/{example_id}` without a session, returning the entry's
identity, resolved configuration that ran, structured evaluation metrics, evaluation success state
separate from infrastructure completion, checkpoint identity, runtime versions, measured runtime and
cost, and the list of publicly available artifacts with opaque identifiers, human-readable names,
kinds, content types, sizes, and public access URLs. Nested metric objects SHALL be returned as
structured data.

#### Scenario: Anonymous visitor opens an example
- **WHEN** a client requests a published example ID with no credentials
- **THEN** the API returns its resolved configuration, structured metrics, evaluation state, and
  artifact list with public access URLs

#### Scenario: Unknown or unpublished example is requested
- **WHEN** a client requests an example ID that is unknown, hidden, or failing its evidence gate
- **THEN** the API returns 404 without revealing which of those cases applies

#### Scenario: Evaluation outcome is reported honestly
- **WHEN** a pinned run finished artifact production but did not meet its task threshold
- **THEN** the detail reports the completed run with an unmet-threshold evaluation state rather than
  implying success

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
