## MODIFIED Requirements

### Requirement: Job composer
The web app SHALL make the production-executable `/training-options` catalog a gallery of exactly
seven trainable example cards. Each card SHALL show its original avatar, task/environment story,
expected result, backend/hardware, one recommended bounded configuration, and observed duration and
cost. The default path SHALL require only selecting a card, reviewing the recommendation, and
starting training. Unsupported or incomplete work SHALL be absent, and validation errors SHALL be
shown next to the offending field without creating an apparent job.

#### Scenario: Browse seven realistic examples
- **WHEN** an authenticated user opens New Job
- **THEN** the UI presents Go1 Walker, Ant Explorer, HalfCheetah Sprint, Hopper Balance, Walker2D
  Stride, Humanoid Walk, and Reacher Target as seven responsive cards

#### Scenario: Review a recommended configuration
- **WHEN** the user selects a card
- **THEN** a concise review shows the expected result, observed duration/cost, backend/hardware, and
  recommended bounded configuration before the Start training action

#### Scenario: Unsupported work is absent
- **WHEN** the production catalog omits an incomplete or unaccepted example
- **THEN** the composer provides no card or stale control capable of submitting it

#### Scenario: Compose and submit a gallery job
- **WHEN** an authenticated user selects an accepted card and starts training
- **THEN** the job is created from the card's stable example ID and appears in the dashboard without
  a page reload

#### Scenario: Validation failure stays in context
- **WHEN** a declared optional field is outside its catalog bounds
- **THEN** the field shows the violation and the submit action remains disabled until corrected

### Requirement: Browser media player and artifact actions
The results view SHALL embed manifest-declared MP4 artifacts in an accessible HTML5 video player,
designate the final rollout as primary media when present, allow selection among progression and
intermediate videos, and provide a primary **Download policy bundle** action for completed gallery
jobs with a validated bundle. Individual open/download actions SHALL remain available under
secondary result files. All actions SHALL use tenant-authorized artifact URLs, and media SHALL
support seeking without loading the entire file first.

#### Scenario: Play final rollout
- **WHEN** a completed job contains a final MP4 rollout
- **THEN** the results view displays it as the primary player with native play, pause, seek, volume,
  fullscreen, and accessibility controls

#### Scenario: Select progression media
- **WHEN** a completed job contains final, intermediate, untrained, and progression montage videos
- **THEN** the user can select each by a human-readable label without navigating away

#### Scenario: Download policy bundle
- **WHEN** a completed gallery result declares a validated policy bundle
- **THEN** the compact result header offers Download policy bundle and explains that it targets the
  matching simulator rather than a physical robot

#### Scenario: Download individual artifact
- **WHEN** the user opens secondary result files and selects a manifest-declared artifact
- **THEN** the browser receives the tenant-authorized object with a safe filename

#### Scenario: Media becomes unavailable
- **WHEN** artifact access returns an expired, missing, or authorization error
- **THEN** the player shows a human-readable unavailable state and offers a safe retry that obtains
  fresh artifact metadata

## ADDED Requirements

### Requirement: Compact browser-first result overview
The completed result page SHALL put a compact summary above diagnostic details: example avatar and
identity, completion/evaluation state, primary KPI, runtime, cost, final rollout, checkpoint
identity, and the policy-bundle action. Resolved configuration, versions, raw metrics, device data,
and individual files SHALL be organized into readable labeled sections or collapsed details rather
than equal-width raw JSON columns.

#### Scenario: Completed result opens on desktop
- **WHEN** the owner opens a completed gallery job
- **THEN** the key outcome and actions fit in a compact overview and nested objects do not render as
  narrow full-height JSON columns

#### Scenario: Completed result opens on mobile
- **WHEN** the result is viewed at 375px width
- **THEN** KPIs, player, actions, and expandable details remain readable without horizontal
  scrolling

#### Scenario: No download is required
- **WHEN** the owner wants only to judge the training outcome
- **THEN** evaluation, rollout, runtime, cost, configuration, checkpoint identity, and versions are
  inspectable in the browser without downloading the bundle

### Requirement: Gallery identity follows the job
Jobs and result views SHALL use the persisted gallery example identity, label, and avatar when
present. Historical jobs without an example identity SHALL fall back to their resolved
environment/profile and SHALL NOT fail rendering.

#### Scenario: Gallery job appears in Jobs
- **WHEN** a user submits Ant Explorer
- **THEN** its dashboard row and detail show the Ant Explorer identity and lifecycle rather than
  only a backend environment string

#### Scenario: Historical job appears in Jobs
- **WHEN** a pre-gallery job is listed
- **THEN** it remains navigable using its existing environment/profile label and generic fallback
  avatar

### Requirement: Honest custom robot validation handoff
The My Robots workspace SHALL distinguish `Model validated` and `Setup validated` from trainable
status. A saved custom setup SHALL explain that its file and bounded environment contract passed,
but uploaded-robot training is not available because no accepted custom training adapter and
production job specification exist. The UI SHALL NOT display an enabled or disabled control that
implies the user can initiate a hidden “GPU validation” stage. It SHALL preserve the setup and offer
an active **Train a verified example** link to the seven-card gallery.

#### Scenario: User saves a custom setup
- **WHEN** model and environment validation succeed
- **THEN** the workspace confirms exactly what was validated, states that no custom training job
  was created, and shows the active gallery link instead of “Training coming after GPU validation”

#### Scenario: User follows the supported training path
- **WHEN** the tenant selects Train a verified example
- **THEN** the app opens the seven-card New Job gallery and leaves the custom robot and setup saved
  unchanged

#### Scenario: User returns to a saved setup
- **WHEN** a tenant later views a validation-only setup
- **THEN** the same honest readiness explanation and gallery action are present with no Start
  Training action for the custom asset
