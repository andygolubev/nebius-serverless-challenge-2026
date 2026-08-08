# saas-robot-assets Specification

## Purpose
Let a tenant upload a bounded, primitive-only MJCF robot model, validate its structure server-side,
and manage immutable versioned copies. Validation here is structural only: a robot version is never
itself trainable, and it reaches training solely by being referenced from a setup that passes the
preparation gate in `custom-robot-training-preparation`.

## Requirements
### Requirement: Constrained tenant robot upload
The system SHALL allow an authenticated tenant to upload one self-contained UTF-8 MJCF `.xml`
file with a name and declared `quadruped` or `biped` type. The upload MUST be at most 1 MiB and
MUST NOT contain an archive, mesh, texture, height field, include, plugin, DTD/entity declaration,
remote reference, external file path, or executable content.

#### Scenario: Valid primitive-only robot is accepted
- **WHEN** a tenant uploads a bounded primitive-only MJCF satisfying the robot structure contract
- **THEN** the API stores an immutable tenant-owned version and returns its identifier, digest,
  validation summary, and `readiness: validated`

#### Scenario: Unsupported content is rejected
- **WHEN** an upload contains an include, mesh, texture, plugin, external path, DTD/entity, archive,
  invalid UTF-8, or exceeds 1 MiB
- **THEN** the API returns 422 with a sanitized field-level diagnostic and persists no robot

#### Scenario: Malformed XML is rejected
- **WHEN** the uploaded content is not well-formed MJCF XML
- **THEN** the API returns a sanitized validation error without echoing the file content

### Requirement: Bounded robot structure validation
The validator SHALL require one floating robot root, at least one controllable hinge joint, unique
names, and actuators that reference existing joints. It SHALL enforce limits of 64 bodies, 64
joints, 64 actuators, 128 geoms, and XML depth 16, and SHALL allow only primitive geometry.

#### Scenario: Actuator references an unknown joint
- **WHEN** a robot actuator names a joint absent from the uploaded model
- **THEN** validation fails before persistence and identifies the invalid actuator reference

#### Scenario: Structural limit is exceeded
- **WHEN** a model exceeds a body, joint, actuator, geom, or depth limit
- **THEN** validation fails with the applicable limit and does not partially store the model

#### Scenario: Validation summary is returned
- **WHEN** a model passes validation
- **THEN** the response includes deterministic body, joint, actuator, and geom counts plus the
  normalized joint and actuator names

### Requirement: Immutable versioning and tenant isolation
Each accepted upload SHALL receive a content SHA-256 digest and immutable version identifier.
Robot list, detail, content-download, and deletion operations SHALL derive tenant ownership from
the authenticated session and SHALL return 404 for another tenant's identifier.

#### Scenario: Identical upload is idempotent
- **WHEN** the same tenant uploads identical XML with the same declared robot type
- **THEN** the API returns the existing active robot version instead of storing duplicate content

#### Scenario: Another tenant requests the robot
- **WHEN** an authenticated tenant requests another tenant's robot identifier or content
- **THEN** the API returns 404 without revealing whether the robot exists

#### Scenario: Tenant deletes a robot
- **WHEN** the owning tenant deletes a robot version
- **THEN** the robot is hidden from normal list and detail routes without affecting jobs or other
  tenants

### Requirement: Canonical sample robot files
The repository SHALL contain original primitive-only quadruped and biped MJCF sample files that
pass the same validator and limits as tenant uploads. Authenticated API routes SHALL list and
download these exact examples with their type, description, filename, and digest.

#### Scenario: Samples remain upload-compatible
- **WHEN** automated verification loads both repository sample files
- **THEN** each file passes the public upload validator without a sample-only exception

#### Scenario: User downloads and uploads a sample
- **WHEN** a tenant downloads a listed sample and submits it through the normal robot upload route
- **THEN** the API accepts it and returns the same structural digest and type metadata

### Requirement: Honest custom robot readiness
A structurally valid custom robot SHALL be represented as `readiness: validated` and
`trainable: false` with reason `custom-training-not-enabled`. Training readiness is a property of a
*setup*, not of a robot: a robot version alone SHALL never be trainable, and the API and UI SHALL
distinguish structural validation from training readiness rather than implying a robot is ready to
run.

#### Scenario: Validated robot is inspected
- **WHEN** a tenant views an accepted custom robot
- **THEN** the API and UI report structural validation only, and the offered next action is to build
  a setup rather than to start training

#### Scenario: Robot is not a submission identity
- **WHEN** a client supplies a robot identifier to any job-creating route
- **THEN** the request is rejected and no job or remote resource is created, because training is
  started only from an accepted setup
