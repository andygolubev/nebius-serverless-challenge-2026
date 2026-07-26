## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Bundle-gated completion for new gallery jobs
**Reason**: No new gallery job can be created, so a completion gate for new gallery jobs governs an empty
set. Bundle-gated completion for custom jobs is already required by "Custom job finalization requires the
complete result set" in `saas-artifact-access`.
**Migration**: Showcase publication is gated instead by "Evidence-gated publication" in
`public-training-showcase`, which withholds an entry whose pinned run lacks a readable, digest-valid
bundle. Historical completed gallery jobs remain readable exactly as they are, with or without a bundle.
