# saas-environment-builder Specification

## Purpose
Let a tenant compose a training environment from one owned validated robot, a server-owned
locomotion task, a scene preset, and bounded catalog objects — entirely from declarative,
server-owned choices, with no tenant-supplied code, mesh, or environment file.

## Requirements
### Requirement: Server-owned locomotion task templates
The system SHALL expose a declarative task catalog containing `stand-balance` and `walk-forward`
for validated bipeds and quadrupeds and `recover-from-fall` for validated quadrupeds only. Each
template SHALL provide a human label, description, compatible robot types, and future training
contract metadata without accepting tenant reward, observation, termination, or executable code.

#### Scenario: Compatible task is selected
- **WHEN** a tenant selects `walk-forward` for a validated biped or quadruped
- **THEN** the environment draft resolves the server-owned template and records no tenant code

#### Scenario: Incompatible task is rejected
- **WHEN** a tenant selects `recover-from-fall` for a biped
- **THEN** the API returns 422 naming the task compatibility error and saves no draft

### Requirement: Bounded scene and object catalog
The system SHALL expose server-owned `flat-arena`, `ramp-course`, `hurdle-course`, and
`step-course` scene presets and the primitive object types `box`, `ramp`, `hurdle`, and `step`.
Every object parameter SHALL have server-declared defaults and numeric bounds, and a draft SHALL
contain at most six objects inside the declared arena bounds.

#### Scenario: Preset environment is used unchanged
- **WHEN** a tenant selects a scene preset without custom objects
- **THEN** the server persists the preset's normalized server-owned object composition

#### Scenario: Bounded catalog object is added
- **WHEN** a tenant adds an allowlisted object with in-range position, rotation, and dimensions
- **THEN** the server resolves defaults and includes the normalized object in the draft

#### Scenario: Unsupported or excessive object is rejected
- **WHEN** a draft contains an unknown object type, an out-of-range value, an out-of-arena
  position, or more than six objects
- **THEN** the API returns 422 with a field-level error and persists no partial draft

### Requirement: Tenant environment drafts
An authenticated tenant SHALL be able to create, list, inspect, and delete environment drafts
composed from one owned validated robot, one compatible task template, one scene preset, and
bounded catalog objects. The server SHALL persist the fully normalized configuration and SHALL
enforce tenant ownership for both the draft and referenced robot.

#### Scenario: Valid setup is saved
- **WHEN** a tenant submits an owned robot with compatible task and bounded scene configuration
- **THEN** the API stores and returns an immutable normalized environment draft with a content
  digest and `readiness: validated`

#### Scenario: Cross-tenant robot is referenced
- **WHEN** a tenant attempts to build a draft using another tenant's robot identifier
- **THEN** the API returns 404 and stores no draft

#### Scenario: Draft persists across restart
- **WHEN** the backend restarts after a tenant saves an environment draft
- **THEN** the same tenant can list and inspect the identical normalized draft afterward

### Requirement: No custom object or environment-file upload
The beta SHALL NOT accept object meshes, object XML, scene files, environment packages, remote
URLs, or executable task definitions. It SHALL direct users to the validated server-owned scene
and object catalog.

#### Scenario: Object file is submitted
- **WHEN** a client attempts to submit a mesh, object file, URL, or unknown file field while
  building an environment
- **THEN** the API rejects the request before persistence and identifies the supported catalog
  workflow

### Requirement: Honest environment readiness
A saved draft SHALL report `readiness: validated` for its structural composition and SHALL carry a
separate derived `training_readiness` that never conflates the two. `trainable` SHALL be true only
while the setup has a current accepted preparation fingerprint. A draft SHALL NOT appear in
`/training-options` and SHALL NOT be accepted by any general job route; the only way to train it is
the setup-bound route defined in `saas-job-customization`.

#### Scenario: Validated draft is completed
- **WHEN** a tenant finishes a valid robot/task/scene composition
- **THEN** the UI labels it `Validated setup`, states that no training job was created, and offers
  the preparation action rather than a Start Training action

#### Scenario: Structural validity is not training readiness
- **WHEN** a catalog-valid draft has no accepted preparation for its current fingerprint
- **THEN** it reports `trainable: false` with a stable reason and Start training is refused before
  any local or remote job creation

#### Scenario: Draft is never a public catalog entry
- **WHEN** any client fetches `/training-options`
- **THEN** no tenant robot, setup, or custom profile appears in the response
