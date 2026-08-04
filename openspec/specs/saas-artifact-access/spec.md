# saas-artifact-access Specification

## Purpose
Provide secure, tenant-facing access to durable training artifacts in Nebius Object Storage and
ensure submitted training jobs write to the same per-run S3 prefixes without exposing credentials.
## Requirements
### Requirement: S3 artifact reads
The SaaS backend SHALL read status, metrics, manifests, and media metadata from the configured artifact bucket through the S3 API, scoped to `sim2policy/<run-id>/`. A job SHALL NOT be considered `completed` until its required finalized artifact set is readable and valid. `GET /jobs/{job_id}/artifacts` SHALL return structured readiness and artifact metadata rather than raw object keys; transient absence during finalization SHALL remain distinguishable from terminal artifact failure.

#### Scenario: Finalized job returns structured artifacts
- **WHEN** a tenant requests artifacts for a finalized job they own
- **THEN** the API returns metrics plus artifact identifiers, names, kinds, content types, sizes when known, and tenant-authorized access URLs without returning bucket credentials or bare object keys as browser links

#### Scenario: Artifacts are still finalizing
- **WHEN** remote training succeeded but the required artifact set is not yet complete
- **THEN** the API returns a structured not-ready response and the job remains non-terminal

#### Scenario: Lazy recovery after publication
- **WHEN** finalization publishes a valid manifest after an earlier transient read failure
- **THEN** reconciliation reads and validates it, caches the manifest durably, and allows the job to become `completed`

#### Scenario: Invalid finalized manifest fails safely
- **WHEN** a manifest references a missing, unsafe, or out-of-prefix object
- **THEN** the backend refuses to expose the reference and records a sanitized artifact-validation failure

#### Scenario: Completed job returns real artifacts
- **WHEN** a finalized Nebius-backed job's owner requests its artifacts
- **THEN** the response is derived from validated objects under the run prefix and contains structured artifact metadata rather than in-process placeholders

#### Scenario: Artifacts not yet written
- **WHEN** required finalized artifacts are not yet readable
- **THEN** the artifact API returns structured not-ready state and the job remains non-terminal

#### Scenario: Manifest published after job completion
- **WHEN** a historical completed job has no cached manifest and finalization later publishes `report/artifacts.json`
- **THEN** an owner request reads, validates, and durably caches the manifest before returning structured artifacts

#### Scenario: Lazy read failure degrades to not-ready
- **WHEN** an on-demand historical manifest read encounters a missing key or transient S3 error
- **THEN** the API reports artifacts not ready without leaking the storage error or returning an unhandled 5xx

### Requirement: S3 credentials injected from MysteryBox

S3 credentials for the SaaS pod SHALL be sourced from MysteryBox and delivered to the container as environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_DEFAULT_REGION`, `SIM2POLICY_S3_BUCKET`). The secret access key SHALL NOT appear in Git, in plain Kubernetes manifests, or in logs.

#### Scenario: Pod receives credentials from a secret

- **WHEN** the SaaS deployment starts in the cluster
- **THEN** the S3 env vars are populated from a Kubernetes Secret whose values originate in MysteryBox, and no manifest in Git contains the secret access key

#### Scenario: Missing credentials fail fast

- **WHEN** the `nebius` backend is selected but the S3 credentials are absent
- **THEN** the service reports a configuration error at startup rather than failing on the first tenant request

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

### Requirement: Tenant-authorized artifact delivery
The backend SHALL expose an opaque artifact access URL for each manifest-declared artifact. Every access SHALL authenticate the session, verify ownership of the job, resolve an allowlisted artifact identifier against the cached manifest, and either stream the object with HTTP range support or redirect to a short-lived presigned HTTPS URL. Callers SHALL NOT supply arbitrary bucket keys or prefixes.

#### Scenario: Owner plays a video
- **WHEN** the owning tenant requests an MP4 artifact through its access URL
- **THEN** the response supports browser playback and byte-range seeking with the correct `video/mp4` content type

#### Scenario: Owner downloads an artifact
- **WHEN** the owning tenant invokes the artifact download action
- **THEN** the backend returns or redirects to the exact manifest-declared object with a safe filename and appropriate content-disposition

#### Scenario: Another tenant is denied
- **WHEN** an authenticated tenant requests an artifact belonging to another tenant
- **THEN** the API returns 404 without revealing whether the job or artifact exists

#### Scenario: Arbitrary object key is rejected
- **WHEN** a caller supplies an object key or artifact identifier not present in the owned job's validated manifest
- **THEN** the API returns 404 and performs no S3 read for the caller-supplied key

### Requirement: Policy bundle artifact delivery
The artifact API SHALL represent a finalized `policy-bundle.zip` as a manifest-declared artifact
with an opaque identifier, safe filename, `application/zip` content type, byte size, and SHA-256
digest. Access SHALL reuse the tenant-authorized artifact route: authenticate the session, verify
job ownership, resolve only the cached allowlisted identifier, and stream or redirect to a
short-lived presigned HTTPS URL. A client SHALL NOT provide a bucket key or prefix.

#### Scenario: Owner requests policy bundle metadata
- **WHEN** the owning tenant requests artifacts for a completed gallery job
- **THEN** the structured response includes the bundle's opaque identifier, safe display name,
  size, digest, and tenant-authorized download URL without exposing its object key

#### Scenario: Owner downloads policy bundle
- **WHEN** the owning tenant follows the bundle download URL
- **THEN** the exact validated archive is returned or redirected with `application/zip` and a safe
  attachment filename

#### Scenario: Another tenant requests the bundle
- **WHEN** an authenticated tenant requests a bundle belonging to another tenant
- **THEN** the API returns 404 and reveals neither the job nor artifact existence

#### Scenario: Caller supplies an arbitrary bundle key
- **WHEN** a caller supplies a storage key or identifier not in the owned job's cached manifest
- **THEN** the API returns 404 and performs no S3 read for the caller-supplied value

### Requirement: Policy bundle integrity before exposure
The backend SHALL expose a policy bundle only after validating the archive's outer SHA-256 digest,
bounded safe member list, required common-envelope files, internal manifest schema, and every
declared member digest. Validation failures SHALL be sanitized and SHALL NOT expose a partial or
untrusted archive.

#### Scenario: Bundle validates
- **WHEN** the readable archive matches its outer digest and all required members match the
  internal manifest
- **THEN** it is cached as a validated artifact and may participate in gallery-job completion

#### Scenario: Bundle digest or member is invalid
- **WHEN** an archive is corrupt, missing a required file, contains an unsafe path, or disagrees
  with its declared digest
- **THEN** it is not returned to the tenant and finalization records a sanitized validation failure

### Requirement: Custom input and result prefixes are server-scoped
The SaaS backend and trusted runtime SHALL read/write custom preparation inputs only beneath `sim2policy/preparations/<preparation-id>/` and custom training snapshots/results only beneath `sim2policy/<run-id>/`, where both identities are generated and ownership-resolved by the server. Tenant APIs SHALL expose opaque attempt/job/artifact identifiers and SHALL never accept or return a bare input/result key as an authority to read storage.

#### Scenario: Runtime receives a custom input reference
- **WHEN** a typed preparation or training job resolves its inputs
- **THEN** the prefix is reconstructed from the server identity, checked for safe containment, and matched to the expected manifest before any object is trusted

#### Scenario: Caller supplies a storage key
- **WHEN** a tenant attempts to request, prepare, train, or download using an arbitrary bucket key or prefix
- **THEN** the API rejects or ignores the field and performs no caller-directed S3 access

### Requirement: Custom job finalization requires the complete result set
For a custom-robot Job, artifact finalization SHALL require a valid manifest entry and readable in-prefix object for evaluation metrics and episodes, human summary/reward curve, final rollout MP4, final checkpoint, resolved configuration/runtime metadata, exact input snapshots, and simulator policy bundle. Every entry SHALL have a safe identifier/name, expected kind/content type, byte size, and integrity metadata. The Job SHALL not become completed while any required object is missing or invalid.

#### Scenario: Complete custom manifest is read
- **WHEN** all required custom artifacts exist beneath the owned run prefix and validate
- **THEN** the backend caches their structured metadata, completes the Job, and exposes normal tenant-authorized player/download controls

#### Scenario: Manifest points outside the run
- **WHEN** a custom manifest entry references the preparation prefix, another run, an absolute URL, or a traversing key instead of its approved run snapshot/artifact
- **THEN** finalization rejects the entry and exposes no access URL

### Requirement: Policy bundle is delivered through normal tenant authorization
The custom policy bundle SHALL be a manifest-declared artifact available only through the existing owned Job artifact-access mechanism, with a safe filename, archive content type, byte size, checksum, and short-lived/streamed access. Cross-tenant requests SHALL return 404, and deleted source robot/setup state SHALL not alter ownership of the historical Job artifact.

#### Scenario: Owner downloads a bundle
- **WHEN** the Job owner requests the manifest-declared policy bundle
- **THEN** the backend streams or redirects to exactly that object using a safe filename and appropriate content disposition

#### Scenario: Another tenant requests a bundle
- **WHEN** another authenticated tenant uses the custom Job or artifact identifier
- **THEN** the API returns 404 without revealing whether the bundle exists

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

