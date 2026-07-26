## ADDED Requirements

### Requirement: Public showcase artifact reads
The backend SHALL read status, metrics, manifests, and media metadata for a server-pinned showcase run
through the S3 API, scoped to `sim2policy/<pinned-run-id>/`, where the pinned run identity comes only
from server-owned source. A showcase read SHALL validate the manifest, refuse any entry referencing a
missing, unsafe, out-of-prefix, or digest-mismatched object, and durably cache the validated result so
anonymous traffic does not re-crawl storage. A read failure SHALL degrade to an unpublished entry, not
a 5xx.

#### Scenario: Pinned run manifest is read and cached
- **WHEN** a showcase entry's pinned run publishes a valid `report/artifacts.json`
- **THEN** the backend validates it, caches the structured metadata durably under the pinned run
  identity, and serves subsequent anonymous requests from the cache

#### Scenario: Pinned run manifest is absent
- **WHEN** a pinned run has produced no manifest
- **THEN** the entry is reported unpublished and the request returns 404 without a storage error
  leaking

#### Scenario: Pinned manifest references an out-of-prefix object
- **WHEN** a showcase manifest entry names an object outside `sim2policy/<pinned-run-id>/`, an absolute
  URL, or a traversing key
- **THEN** the backend refuses the entry, withholds the whole showcase entry, and records a sanitized
  validation failure

#### Scenario: Showcase cache is keyed by pinned run
- **WHEN** the showcase and a tenant job are both cached
- **THEN** their cache entries are keyed by distinct identities and a showcase lookup cannot return a
  tenant job's manifest

### Requirement: Public showcase artifact delivery
The backend SHALL expose an opaque public access URL for each showcase-published artifact of a pinned
run. Every access SHALL resolve the example ID to its pinned run, resolve an allowlisted artifact
identifier against that run's cached validated manifest, and either stream the object with HTTP range
support or redirect to a short-lived presigned HTTPS URL. No session SHALL be required. Callers SHALL
NOT supply bucket keys, prefixes, run identities, or content dispositions. This route SHALL be
structurally incapable of resolving a tenant-owned run, and the bucket SHALL remain private.

#### Scenario: Anonymous visitor plays a showcase video
- **WHEN** an unauthenticated client requests a published example's MP4 through its public access URL
- **THEN** the response supports browser playback and byte-range seeking with `video/mp4` content type

#### Scenario: Anonymous visitor downloads a showcase file
- **WHEN** an unauthenticated client invokes a published artifact's download action
- **THEN** the backend returns or redirects to exactly that manifest-declared object with a safe
  filename and appropriate content disposition

#### Scenario: Public route is aimed at a tenant run
- **WHEN** a caller substitutes a tenant job ID, tenant run ID, or arbitrary identity for the showcase
  example ID
- **THEN** the API returns 404, performs no read against a tenant prefix, and reveals nothing about the
  tenant run

#### Scenario: Arbitrary artifact identifier is rejected
- **WHEN** a caller supplies an artifact identifier or object key absent from the pinned run's
  validated manifest
- **THEN** the API returns 404 and performs no S3 read for the caller-supplied value

#### Scenario: Public presigned exposure is bounded
- **WHEN** the backend issues a presigned URL for a showcase artifact
- **THEN** it is short-lived, read-only, scoped to one validated in-prefix object, and grants no list,
  write, or sibling access

### Requirement: Public and tenant artifact boundaries stay separate
The public showcase artifact surface and the tenant-authorized artifact surface SHALL be distinct code
paths with distinct identity resolution. The public surface SHALL never consult session state or tenant
ownership to widen access, and the tenant surface SHALL never accept a showcase example ID as authority
to read a job. No pinned showcase run identity SHALL collide with a tenant job or run identity.

#### Scenario: Public path ignores session state
- **WHEN** a request to a public showcase artifact route carries a valid tenant bearer token
- **THEN** access is determined solely by the pinned-run allowlist and the token grants nothing extra

#### Scenario: Tenant path rejects a showcase identity
- **WHEN** a caller passes a showcase example ID to a tenant job artifact route
- **THEN** the API returns 404 under normal ownership resolution

#### Scenario: Identity spaces do not collide
- **WHEN** pinned showcase run identities are validated at startup
- **THEN** each is confirmed distinct from the tenant job identity space and unsafe or colliding values
  prevent publication of that entry

## MODIFIED Requirements

### Requirement: Training jobs share the artifact credentials

Each submitted Serverless AI job SHALL receive the artifact-bucket credentials, with the secret access
key injected via MysteryBox secret reference (the SDK equivalent of `--env-secret`), so the training
container writes its outputs to `s3://sim2policy-artifacts/sim2policy/<run-id>/`. Curated showcase runs
SHALL write under the same layout so a pinned run is readable by the public showcase without any
special storage arrangement or public bucket policy.

#### Scenario: Training output lands under the run prefix

- **WHEN** a submitted training job completes
- **THEN** its checkpoints, manifest, and media exist under the job's `sim2policy/<run-id>/` prefix and
  are readable by the SaaS backend

#### Scenario: Secret key never passed in plaintext

- **WHEN** the backend constructs the job submission
- **THEN** the AWS secret access key is referenced through MysteryBox, never embedded as a plaintext env
  value in the job spec or logged

#### Scenario: Curated run is readable by the showcase

- **WHEN** a curated showcase run finishes and its identity is pinned in server-owned source
- **THEN** the showcase reads it through the same private-bucket S3 path with no bucket ACL, public
  prefix, or credential change
