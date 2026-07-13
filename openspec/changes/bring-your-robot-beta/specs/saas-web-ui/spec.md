## ADDED Requirements

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

