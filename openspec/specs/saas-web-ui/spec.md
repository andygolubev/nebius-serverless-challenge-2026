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
The web app SHALL render the production-executable `/training-options` catalog and present at least three GPU-accelerated PPO workload profiles: Go1 Quick, Go1 Standard, and Go1 Quality. Each profile SHALL show its bounded workload size and observed duration/cost guidance. The composer SHALL NOT present SB3, CPU-bound-on-GPU, or missing-job-spec options. Submission errors SHALL be shown next to the offending field without creating an apparent job.

#### Scenario: Choose among GPU workload sizes
- **WHEN** an authenticated user opens the composer
- **THEN** the UI presents Quick, Standard, and Quality Go1 MJX PPO profiles with increasing workload and clear duration/cost guidance

#### Scenario: Unsupported work is absent
- **WHEN** the production catalog omits an unsupported environment/algorithm
- **THEN** the composer provides no control or stale preset capable of submitting it

#### Scenario: Client-side validation
- **WHEN** the user types a value outside a profile's declared bounds
- **THEN** the input shows the violation and the submit action is disabled until fixed

#### Scenario: Compose and submit a custom job
- **WHEN** an authenticated user selects one of the three GPU workload profiles and submits it
- **THEN** the executable Go1 MJX job is created and appears in the dashboard without a page reload

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
The results view SHALL embed manifest-declared MP4 artifacts in an accessible HTML5 video player, designate the final rollout as the primary media when present, allow selection among progression and intermediate videos, and provide explicit open and download actions for all supported artifacts. The player SHALL use tenant-authorized artifact URLs and support seeking without loading the entire video first.

#### Scenario: Play final rollout
- **WHEN** a completed job contains a final MP4 rollout
- **THEN** the results view displays it as the primary player with native play, pause, seek, volume, fullscreen, and accessibility controls

#### Scenario: Select progression media
- **WHEN** a completed job contains final, intermediate, untrained, and progression montage videos
- **THEN** the user can select each by a human-readable label without navigating away

#### Scenario: Download artifact
- **WHEN** the user selects Download for a manifest-declared artifact
- **THEN** the browser receives the tenant-authorized object with a safe filename

#### Scenario: Media becomes unavailable
- **WHEN** artifact access returns an expired, missing, or authorization error
- **THEN** the player shows a human-readable unavailable state and offers a safe retry that obtains fresh artifact metadata
