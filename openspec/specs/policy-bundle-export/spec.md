# policy-bundle-export Specification

## Purpose
Package and deliver a deterministic, tenant-authorized policy bundle for completed gallery
training jobs so a user can understand and reproduce a result without inspecting raw diagnostics,
while keeping the checkpoint clearly scoped to its simulator and not implying physical-robot
readiness.

## Requirements
### Requirement: Browser-first training outcome
A completed gallery job SHALL present enough validated information in the browser to understand
the outcome without downloading a file: example identity, primary task KPI, evaluation summary,
runtime, cost, final rollout, checkpoint identity, resolved configuration, and runtime versions.
Raw nested diagnostics SHALL be secondary to this summary.

#### Scenario: User reviews a completed run
- **WHEN** the owner opens a completed gallery job
- **THEN** the result view answers what trained, whether it met its evaluation criterion, how long
  it ran, what it cost, and which checkpoint/runtime produced the rollout without requiring a
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

### Requirement: Bundle-gated completion for new gallery jobs
A new gallery job SHALL NOT become `completed` until its bundle is readable, its outer digest is
known, and its internal manifest and member digests validate. Historical non-gallery jobs MAY
remain completed without a bundle.

#### Scenario: Bundle is ready
- **WHEN** all other required artifacts and a valid policy bundle are readable
- **THEN** the gallery job may transition from finalization to completed

#### Scenario: Bundle finalization fails
- **WHEN** the bundle cannot be created or validated within the bounded finalization deadline
- **THEN** the job becomes failed with phase `finalization` and a sanitized reason rather than
  exposing a broken Download policy bundle action

#### Scenario: Historical result is opened
- **WHEN** a completed job created before the gallery change has no policy bundle
- **THEN** its existing result remains readable and the UI omits the bundle action without error

### Requirement: Optional tenant-authorized bundle download
The completed result SHALL offer a primary **Download policy bundle** action to the owning tenant,
but downloading SHALL NOT be required to view or replay the result. Delivery SHALL use the validated
artifact manifest and existing tenant-authorized streaming or short-lived redirect boundary with a
safe filename.

#### Scenario: Owner downloads the bundle
- **WHEN** the owning tenant selects Download policy bundle
- **THEN** the browser receives the exact validated archive with a safe content disposition and no
  bucket key or credential exposure

#### Scenario: Another tenant requests the bundle
- **WHEN** a different authenticated tenant requests that artifact identifier
- **THEN** the service returns 404 without revealing whether the job or bundle exists

### Requirement: Individual artifacts remain secondary
Validated reports, JSON metrics, checkpoints, and videos SHALL remain available as individual
secondary files when present. The final rollout SHALL remain streamable independently of the
policy bundle.

#### Scenario: User needs only the rollout
- **WHEN** a completed job has final MP4 media
- **THEN** the user can play or download it without downloading the policy archive

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
