# policy-bundle-export Specification

## Purpose
Package and deliver a deterministic, tenant-authorized policy bundle for completed gallery
training jobs so a user can understand and reproduce a result without inspecting raw diagnostics,
while keeping the checkpoint clearly scoped to its simulator and not implying physical-robot
readiness.
## Requirements
### Requirement: Browser-first training outcome
A published showcase entry and a completed custom job SHALL each present enough validated information
in the browser to understand the outcome without downloading a file: identity, primary task KPI,
evaluation summary, runtime, cost, final rollout, checkpoint identity, resolved configuration, and
runtime versions. For a showcase entry this SHALL be available to an unauthenticated visitor. Raw
nested diagnostics SHALL be secondary to this summary.

#### Scenario: Visitor reviews a showcase run
- **WHEN** an anonymous visitor opens a published showcase entry
- **THEN** the view answers what trained, whether it met its evaluation criterion, how long it ran, what
  it cost, and which checkpoint/runtime produced the rollout without requiring a download or an account

#### Scenario: Owner reviews a completed custom run
- **WHEN** the owner opens a completed custom job
- **THEN** the result view answers the same questions from its validated manifest without requiring a
  download

### Requirement: Deterministic policy bundle
Finalization for every new gallery job SHALL create `policy-bundle.zip` containing `README.md`,
`manifest.json`, `resolved-config.json`, `evaluation/metrics.json`, `runtime/versions.json`, and the
final backend-native checkpoint beneath `checkpoint/`. Member paths, order, timestamps, and JSON
serialization SHALL be normalized so identical finalized inputs produce an identical SHA-256
bundle digest. The bundle SHALL exclude credentials, tenant session data, storage keys, logs, and
rollout video.

#### Scenario: Gallery run finalizes successfully
- **WHEN** training has produced a final checkpoint and validated evaluation metadata
- **THEN** finalization publishes one deterministic bundle whose manifest lists every member's
  safe path, size, media type, and SHA-256 digest

#### Scenario: Bundle is regenerated from identical inputs
- **WHEN** the packager receives byte-identical checkpoint and canonical metadata inputs twice
- **THEN** both archives and their reported SHA-256 digests are byte-identical

#### Scenario: Unsafe archive input is encountered
- **WHEN** an input has an absolute path, traversal segment, duplicate normalized name, excessive
  size/count, or unsupported member type
- **THEN** packaging fails safely and publishes no partial bundle

### Requirement: Bundle compatibility guidance
The bundle README and manifest SHALL identify the example, backend, simulator/environment, library
versions, immutable runtime image, checkpoint loader contract, and evaluation command. They SHALL
state that the checkpoint is for the matching simulator/runtime and is not directly deployable to
a physical robot without separate adaptation and safety validation.

#### Scenario: User opens bundle instructions
- **WHEN** a user reads `README.md`
- **THEN** they receive bounded reproduction/evaluation instructions plus the simulator-only and
  physical-robot limitation in plain language

#### Scenario: Backend-native checkpoint is exported
- **WHEN** an SB3 or MJX job is bundled
- **THEN** the original checkpoint format is preserved and the manifest names the matching loader
  rather than claiming a universal model format

### Requirement: Optional tenant-authorized bundle download
A completed custom job's result SHALL offer a primary **Download policy bundle** action to the owning
tenant, and a published showcase entry SHALL offer the same action to any visitor through the public
showcase artifact route. Downloading SHALL NOT be required to view or replay either result. Delivery
SHALL use the validated artifact manifest and the streaming or short-lived-redirect boundary appropriate
to its surface — tenant-authorized for an owned job, pinned-run-allowlisted for a showcase entry — with
a safe filename and no bucket key or credential exposure. The simulator-only disclosure SHALL be shown
before download on both surfaces.

#### Scenario: Owner downloads the bundle
- **WHEN** the owning tenant selects Download policy bundle on a custom job
- **THEN** the browser receives the exact validated archive with a safe content disposition and no bucket
  key or credential exposure

#### Scenario: Visitor downloads a showcase bundle
- **WHEN** an anonymous visitor selects Download policy bundle on a published showcase entry
- **THEN** the UI first states that the checkpoint is simulator-only and then delivers the exact
  validated archive through the public showcase artifact route

#### Scenario: Another tenant requests the bundle
- **WHEN** a different authenticated tenant requests an owned custom job's artifact identifier
- **THEN** the service returns 404 without revealing whether the job or bundle exists

#### Scenario: Unpublished showcase bundle is requested
- **WHEN** a visitor requests a bundle for an example whose pinned run is unpublished or whose bundle
  failed validation
- **THEN** the service returns 404 and the UI omits the action rather than offering a broken download

### Requirement: Individual artifacts remain secondary
Validated reports, JSON metrics, checkpoints, and videos SHALL remain available as individual secondary
files when present, on both the tenant-authorized and public showcase surfaces. The final rollout SHALL
remain streamable independently of the policy bundle.

#### Scenario: User needs only the rollout
- **WHEN** a completed custom job or published showcase entry has final MP4 media
- **THEN** the user can play or download it without downloading the policy archive

#### Scenario: Visitor opens secondary showcase files
- **WHEN** an anonymous visitor expands a published entry's secondary files
- **THEN** each manifest-declared artifact is listed with a human-readable name and a public access URL

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

