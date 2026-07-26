# saas-web-ui Specification

## Purpose
Provide the styled tenant-facing web application: passwordless login flow, a catalog-driven job
composer, a live jobs dashboard, and results views — built on a consistent, accessible,
light/dark-aware design system that works from mobile to desktop.
## Requirements
### Requirement: Login flow UI
The web app SHALL present an unauthenticated user with a polished login screen: an email entry step, then a code entry step with a resend option and clear error states (wrong code, expired code, rate limited). On success the session token SHALL be stored client-side and the user routed to the dashboard; on 401 anywhere in the app the user SHALL be returned to login.

#### Scenario: Email then code
- **WHEN** a user enters their email and submits
- **THEN** the UI advances to a code-entry step telling the user a code was sent, with a resend action

#### Scenario: Wrong code feedback
- **WHEN** the user submits an incorrect code
- **THEN** the UI shows an inline error and lets the user retry or resend without restarting the flow

#### Scenario: Session expiry
- **WHEN** any API call returns 401 while using the app
- **THEN** the UI clears the stored session and shows the login screen

### Requirement: Job composer
The web app SHALL make the production-executable `/training-options` catalog a gallery of exactly
seven trainable example cards. Each card SHALL show its original avatar, task/environment story,
expected result, backend/hardware, one recommended bounded configuration, and observed duration and
cost. Backend and hardware SHALL be informational metadata selected by the server-owned card; the
composer SHALL NOT expose a global SB3/MJX or compute selector. The default path SHALL require only
selecting a card, reviewing the recommendation, and starting training. Unsupported or incomplete
work SHALL be absent, and validation errors SHALL be shown next to the offending field without
creating an apparent job.

#### Scenario: Browse seven realistic examples
- **WHEN** an authenticated user opens New Job
- **THEN** the UI presents Go1 Walker, Ant Explorer, HalfCheetah Sprint, Hopper Balance, Walker2D
  Stride, G1 Rough Terrain, and Reacher Target as seven responsive cards

#### Scenario: Review a recommended configuration
- **WHEN** the user selects a card
- **THEN** a concise review shows the expected result, observed duration/cost, backend/hardware, and
  recommended bounded configuration before the Start training action

#### Scenario: Backend is not a user choice
- **WHEN** a user reviews any gallery example
- **THEN** its accepted SB3 or MJX backend and hardware are visible as badges with no control to
  change either value

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

### Requirement: Jobs dashboard
The web app SHALL show tenant jobs with live lifecycle, artifact-readiness, relative timestamps, and stale-state indications. A failed job detail SHALL show its sanitized reason and failure phase; operator-visible remote identity SHALL be presented only where authorized. A completed job SHALL link to a results view with structured metrics and validated artifact controls, while finalizing jobs SHALL display their current phase rather than an indefinite skeleton.

#### Scenario: Live status updates
- **WHEN** a submitted job progresses through training and finalization
- **THEN** the dashboard reflects the persisted phase within a few seconds without user action

#### Scenario: Finalization is explicit
- **WHEN** remote training succeeded but artifacts are still being produced
- **THEN** the job detail shows finalization progress and does not label the job completed

#### Scenario: Failed job is actionable
- **WHEN** a job fails
- **THEN** its detail view displays the sanitized failure phase, reason, last update, and retry guidance without exposing secrets or raw stack traces

#### Scenario: Nested metrics remain readable
- **WHEN** result metrics contain nested objects or arrays
- **THEN** the UI renders summaries and expandable structured values rather than `[object Object]`

#### Scenario: Results view
- **WHEN** the user opens a completed job
- **THEN** the UI shows its resolved profile, structured metrics, and validated player/download controls from the artifact manifest

#### Scenario: Empty state
- **WHEN** an authenticated user with no jobs opens the dashboard
- **THEN** the UI guides them to create one of the available GPU workload profiles

### Requirement: Visual design system
The web app SHALL use a consistent design system: defined color tokens with light and dark theme support (respecting `prefers-color-scheme`), a consistent type scale and spacing scale, accessible contrast (WCAG AA), keyboard-operable forms, and a responsive layout usable from 375px-wide mobile up to desktop. Loading and error states SHALL be designed (skeletons/spinners and human-readable messages), not raw text dumps.

#### Scenario: Dark mode
- **WHEN** the user's OS is set to dark mode
- **THEN** the app renders with the dark token set with no unreadable elements

#### Scenario: Mobile layout
- **WHEN** the app is viewed at 375px width
- **THEN** login, composer, and dashboard remain fully usable without horizontal scrolling

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

### Requirement: Bring Your Robot workspace
The authenticated web app SHALL provide a **My Robots** workspace that lists the canonical sample
downloads and tenant robot versions, accepts the constrained robot upload form, renders sanitized
validation errors, and displays parsed statistics, digest, robot type, and readiness for accepted
models.

#### Scenario: User uploads a valid sample
- **WHEN** a tenant uploads either canonical sample through the My Robots form
- **THEN** the workspace displays the new validated robot without navigating to the job composer

#### Scenario: User uploads an invalid model
- **WHEN** robot validation returns a field-level error
- **THEN** the workspace keeps the form state, shows the diagnostic next to the relevant field or
  file input, and creates no apparent robot card

#### Scenario: Training readiness is shown honestly
- **WHEN** a tenant opens a validated custom robot
- **THEN** the workspace shows `Validated model`, states that custom GPU training is not enabled,
  and does not display an active Start Training control

### Requirement: Environment builder UI
The web app SHALL let a tenant select a compatible server-owned locomotion task, choose a scene
preset, optionally configure at most six bounded catalog objects, review the normalized setup, and
save it. Unsupported tasks and object values SHALL be prevented client-side and revalidated by the
server.

#### Scenario: User creates a bounded setup
- **WHEN** a tenant chooses an owned robot, compatible task, scene preset, and valid catalog objects
- **THEN** the UI saves and displays a `Validated setup` summary containing the resolved choices

#### Scenario: Object choices replace file upload
- **WHEN** a tenant configures the scene
- **THEN** the UI offers server-owned object cards and bounded controls and provides no object-file,
  environment-code, or URL upload control

#### Scenario: Builder works on mobile and keyboard
- **WHEN** the workspace is used at 375px width or with keyboard-only input
- **THEN** robot upload, task selection, scene selection, object editing, review, and save remain
  operable without horizontal scrolling

### Requirement: Preparation and training actions follow the setup lifecycle
The My Robots setup UI SHALL show training eligibility and one of `Not prepared`, `Preparing`, `Ready for training`, `Preparation failed`, or `Ineligible` with a concise explanation. An eligible saved setup SHALL provide **Prepare for training**; only its latest current accepted fingerprint SHALL enable **Start training**. Preparation failure SHALL show a sanitized phase/reason and Retry action. The UI SHALL NOT show the former misleading “Training coming after GPU validation” state, because V1 custom training is SB3 on CPU.

#### Scenario: User saves an eligible setup
- **WHEN** a user saves a biped Stand Balance setup on Flat Arena with no optional objects
- **THEN** the setup shows Not prepared and an enabled Prepare for training action while Start training is disabled

#### Scenario: Preparation is running
- **WHEN** the latest attempt is non-terminal
- **THEN** the setup shows its current preparation phase, prevents duplicate actions, and refreshes status without requiring a page reload

#### Scenario: Preparation succeeds
- **WHEN** the latest exact fingerprint becomes accepted
- **THEN** the setup shows Ready for training and enables Start training with fixed `custom-ppo-quick` and `cpu-d3` context

#### Scenario: Preparation fails
- **WHEN** the latest attempt fails
- **THEN** the UI keeps Start training disabled and shows safe diagnostic and Retry controls

#### Scenario: Setup is outside V1
- **WHEN** a saved setup uses an unsupported task, scene, or optional object
- **THEN** the UI explains the exact V1 restriction and does not offer Prepare

### Requirement: Custom start creates and opens a normal Job
Starting an accepted setup SHALL submit only the setup identity plus idempotency metadata, show quota or stale-preparation errors inline, and on success create a normal dashboard Job and provide a direct route to its detail. The UI SHALL NOT expose a backend, algorithm, hardware, image, command, PPO, task, scene, or object override at start time.

#### Scenario: User starts training
- **WHEN** the owner selects Start training for a current Ready setup
- **THEN** the UI creates one custom Job, shows its starting lifecycle, and provides navigation to the normal Job detail

#### Scenario: Fingerprint became stale
- **WHEN** Start training returns that the preparation no longer matches current server versions
- **THEN** the UI returns the setup to Not prepared and asks the user to prepare again without showing a false Job

#### Scenario: User double-clicks Start
- **WHEN** the start action is activated repeatedly before the first response completes
- **THEN** the UI disables the action and the server idempotency contract prevents duplicate Jobs

### Requirement: Custom results are compact, complete, and honest
The normal result view for a custom Job SHALL identify the uploaded robot, task, scene, SB3 backend, fixed profile, preparation fingerprint/version, and evaluation success separately from infrastructure completion. It SHALL prioritize rollout video, key evaluation metrics, configuration summary, checkpoint, and policy-bundle download while keeping detailed nested data expandable. The bundle action SHALL display the simulator-only disclosure before download.

#### Scenario: Completed policy missed its task threshold
- **WHEN** a custom Job completed artifact production with `success=false`
- **THEN** the result is shown as Completed with a clear “task threshold not reached” evaluation state rather than as a failed infrastructure job

#### Scenario: User reviews a successful result
- **WHEN** the owner opens a completed custom Job
- **THEN** the compact view shows the final rollout, success metrics, robot/task/scene/profile summary, and safe artifact actions without raw JSON columns

#### Scenario: User downloads the bundle
- **WHEN** the owner selects the policy bundle action
- **THEN** the UI first states that it is simulator-only and then uses the normal tenant-authorized download URL

### Requirement: Browser-driven production acceptance preserves evidence
Production acceptance SHALL be performed through the deployed UI for both canonical repository robots and every supported task/scene combination. The operator SHALL click Prepare, observe Ready, click Start training, open the resulting Jobs, play rollout media, and download/verify bundles. SaaS Job rows and S3 result artifacts created for this acceptance SHALL be retained for user review; temporary compute/build resources SHALL still be cleaned up according to operations policy.

#### Scenario: Canonical acceptance matrix is completed
- **WHEN** release validation claims V1 custom training support
- **THEN** retained production evidence exists for two robots × two tasks × two scenes, including preparation, Job lifecycle, results, video, and bundle checks

#### Scenario: User later opens an acceptance Job
- **WHEN** the user clicks one of the retained Jobs in the deployed UI
- **THEN** its result and authorized artifacts remain available rather than having been deleted by validation cleanup
