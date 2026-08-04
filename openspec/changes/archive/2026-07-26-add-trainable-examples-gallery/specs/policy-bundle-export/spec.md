## ADDED Requirements

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

