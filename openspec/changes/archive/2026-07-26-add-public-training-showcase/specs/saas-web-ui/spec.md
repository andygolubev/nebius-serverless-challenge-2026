## ADDED Requirements

### Requirement: Public showcase is the unauthenticated landing experience
The web app SHALL render the showcase to a visitor with no session, as the default view at the
application root, without redirecting to login and without any flash of a login screen. The showcase
SHALL present each published example as a responsive card with its avatar, task/environment story,
expected result, backend/hardware badges, the configuration its curated run executed, and its
measured duration and cost. Selecting a card SHALL open a read-only result view. The showcase SHALL
be fully usable at 375px width and by keyboard alone.

#### Scenario: Visitor arrives without an account
- **WHEN** a person with no stored session opens the application root
- **THEN** the showcase renders directly with the published example cards and no login prompt blocks
  the content

#### Scenario: Visitor inspects an example
- **WHEN** a visitor selects a showcase card
- **THEN** a read-only result view opens with the run's evaluation state, metrics, resolved
  configuration, checkpoint identity, and rollout media

#### Scenario: Showcase is empty
- **WHEN** no curated run has been published yet
- **THEN** the showcase shows a designed empty state explaining that verified runs are being prepared,
  not a spinner, error, or blank page

#### Scenario: Showcase is responsive and keyboard-operable
- **WHEN** the showcase and an example detail are used at 375px width or with keyboard-only input
- **THEN** card browsing, detail navigation, media controls, and expandable sections remain operable
  without horizontal scrolling

### Requirement: Anonymous media playback
The showcase result view SHALL embed the pinned run's manifest-declared MP4 artifacts in an
accessible HTML5 player without requiring a session, designate the final rollout as primary media,
allow selection among progression and intermediate videos by human-readable label, and support seeking
without loading the whole file first. All media SHALL be requested through public showcase artifact
URLs.

#### Scenario: Visitor plays the final rollout
- **WHEN** an anonymous visitor opens a published example with a final MP4
- **THEN** it plays as the primary player with native play, pause, seek, volume, fullscreen, and
  accessibility controls

#### Scenario: Visitor selects progression media
- **WHEN** a published run contains final, intermediate, untrained, and progression montage videos
- **THEN** the visitor can select each by label without navigating away or signing in

#### Scenario: Showcase media becomes unavailable
- **WHEN** a public artifact request returns an expired, missing, or unavailable response
- **THEN** the player shows a human-readable unavailable state and offers a retry that fetches fresh
  artifact metadata

### Requirement: Showcase offers no training action
The showcase SHALL NOT present any control — enabled, disabled, or explanatory — that implies a
visitor can run, re-run, fork, or queue a showcase example. Its only call to action SHALL be to sign
in and train the visitor's own robot, and that action SHALL lead to the authenticated My Robots
workspace rather than to a gallery submission.

#### Scenario: Visitor looks for a run button
- **WHEN** a visitor inspects a showcase card or detail, signed in or not
- **THEN** no start, run, re-run, retrain, or queue control for that example exists anywhere in the
  view

#### Scenario: Visitor follows the call to action
- **WHEN** a visitor selects the sign-in call to action
- **THEN** the login flow starts and, on success, the user lands where they can upload a robot and
  train it — not on a gallery submission form

#### Scenario: Signed-in user views the showcase
- **WHEN** an authenticated tenant opens the showcase
- **THEN** it renders the same read-only evidence, with the training path pointing at their own
  robots

## MODIFIED Requirements

### Requirement: Login flow UI
The web app SHALL let a visitor reach the login screen deliberately from the public showcase, and
SHALL present a polished flow: an email entry step, then a code entry step with a resend option and
clear error states (wrong code, expired code, rate limited). On success the session token SHALL be
stored client-side and the user routed to the authenticated app; on 401 anywhere in the authenticated
app the user SHALL be returned to the public showcase with the session cleared, not stranded on an
error.

#### Scenario: Email then code
- **WHEN** a user enters their email and submits
- **THEN** the UI advances to a code-entry step telling the user a code was sent, with a resend action

#### Scenario: Wrong code feedback
- **WHEN** the user submits an incorrect code
- **THEN** the UI shows an inline error and lets the user retry or resend without restarting the flow

#### Scenario: Session expiry
- **WHEN** any authenticated API call returns 401 while using the app
- **THEN** the UI clears the stored session and returns the user to the public showcase with a
  sign-in action available

#### Scenario: Login is reachable but not forced
- **WHEN** an unauthenticated visitor browses the showcase
- **THEN** a sign-in action is present and no navigation or API call forces the login screen

### Requirement: Jobs dashboard
The web app SHALL show tenant jobs with live lifecycle, artifact-readiness, relative timestamps, and
stale-state indications. A failed job detail SHALL show its sanitized reason and failure phase;
operator-visible remote identity SHALL be presented only where authorized. A completed job SHALL link
to a results view with structured metrics and validated artifact controls, while finalizing jobs SHALL
display their current phase rather than an indefinite skeleton. The empty state SHALL guide the tenant
toward uploading and preparing their own robot, since that is the only way to create a job.

#### Scenario: Live status updates
- **WHEN** a submitted job progresses through training and finalization
- **THEN** the dashboard reflects the persisted phase within a few seconds without user action

#### Scenario: Finalization is explicit
- **WHEN** remote training succeeded but artifacts are still being produced
- **THEN** the job detail shows finalization progress and does not label the job completed

#### Scenario: Failed job is actionable
- **WHEN** a job fails
- **THEN** its detail view displays the sanitized failure phase, reason, last update, and retry
  guidance without exposing secrets or raw stack traces

#### Scenario: Nested metrics remain readable
- **WHEN** result metrics contain nested objects or arrays
- **THEN** the UI renders summaries and expandable structured values rather than `[object Object]`

#### Scenario: Results view
- **WHEN** the user opens a completed job
- **THEN** the UI shows its resolved profile, structured metrics, and validated player/download
  controls from the artifact manifest

#### Scenario: Empty state
- **WHEN** an authenticated user with no jobs opens the dashboard
- **THEN** the UI guides them to My Robots to upload a robot, build a setup, and prepare it, and
  offers the showcase as an example of what a finished run looks like

### Requirement: Visual design system
The web app SHALL use a consistent design system across both its public and authenticated surfaces:
defined color tokens with light and dark theme support (respecting `prefers-color-scheme`), a
consistent type scale and spacing scale, accessible contrast (WCAG AA), keyboard-operable forms, and a
responsive layout usable from 375px-wide mobile up to desktop. Loading and error states SHALL be
designed (skeletons/spinners and human-readable messages), not raw text dumps.

#### Scenario: Dark mode
- **WHEN** the user's OS is set to dark mode
- **THEN** both the public showcase and the authenticated app render with the dark token set with no
  unreadable elements

#### Scenario: Mobile layout
- **WHEN** the app is viewed at 375px width
- **THEN** showcase, login, My Robots, and dashboard remain fully usable without horizontal scrolling

### Requirement: Honest custom robot validation handoff
The My Robots workspace SHALL distinguish `Model validated` and `Setup validated` from trainable
status, and SHALL explain what a saved setup's validation actually proved. The UI SHALL NOT display an
enabled or disabled control that implies the user can initiate a hidden "GPU validation" stage. It
SHALL preserve the setup and offer an active **See a verified example** link into the public showcase
as reference evidence — never as an alternative training action, since gallery examples cannot be
trained.

#### Scenario: User saves a custom setup
- **WHEN** model and environment validation succeed
- **THEN** the workspace confirms exactly what was validated, states that no training job was created,
  and shows the preparation path plus the showcase reference link

#### Scenario: User follows the showcase link
- **WHEN** the tenant selects See a verified example
- **THEN** the app opens the read-only showcase and leaves the custom robot and setup saved unchanged,
  offering no way to train the showcase example

#### Scenario: User returns to a saved setup
- **WHEN** a tenant later views a validation-only setup
- **THEN** the same honest readiness explanation, preparation action, and showcase reference link are
  present

### Requirement: Gallery identity follows the job
Jobs and result views SHALL use the persisted gallery example identity, label, and avatar when
present, so historical gallery jobs remain fully readable after gallery training is removed. Jobs
without an example identity SHALL fall back to their resolved environment/profile or custom
robot/task identity and SHALL NOT fail rendering.

#### Scenario: Historical gallery job appears in Jobs
- **WHEN** a tenant opens a job created before gallery training was removed
- **THEN** its row and detail show the recorded example identity, label, avatar, metrics, and
  artifacts as before, with no broken re-run affordance

#### Scenario: Pre-gallery job appears in Jobs
- **WHEN** a job with no example identity is listed
- **THEN** it remains navigable using its existing environment/profile label and generic fallback
  avatar

#### Scenario: Custom job appears in Jobs
- **WHEN** a custom-robot job is listed
- **THEN** it shows its robot, task, and scene identity rather than a gallery association

## REMOVED Requirements

### Requirement: Job composer
**Reason**: The seven-card composer existed to submit gallery examples. With gallery training removed
there is nothing for it to submit, and keeping a card-selection-then-start flow in the UI would promise
an action the API refuses.
**Migration**: The seven cards move to the public read-only showcase (see "Public showcase is the
unauthenticated landing experience"). The authenticated navigation drops "New Job"; the training entry
point is the My Robots workspace, where an owner prepares a setup and starts it. `Composer.tsx` and
its composer-submission tests are deleted.
