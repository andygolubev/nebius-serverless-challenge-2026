## ADDED Requirements

### Requirement: Custom preparation and training provenance persists
The SaaS backend SHALL durably persist tenant-scoped preparation attempts, lifecycle phase/status, fingerprints, input-manifest identity, immutable runtime/profile/schema versions, remote identity, sanitized failure information, timestamps, and accepted report metadata. Normal Job records created from custom setups SHALL durably persist robot, setup, preparation, fingerprint, and immutable input snapshot provenance. Additive schema migration SHALL preserve all existing users, sessions, robots, setups, jobs, and artifact manifests.

#### Scenario: Preparation survives restart
- **WHEN** the backend restarts after a preparation attempt was created or accepted
- **THEN** the owner sees the same attempt, readiness, fingerprint, remote identity, and safe diagnostics without duplicate submission

#### Scenario: Custom Job survives source deletion
- **WHEN** an owner soft-deletes the robot/setup used by a historical custom Job
- **THEN** the Job and preparation provenance remain tenant-readable and continue to reference the immutable run/preparation snapshots

#### Scenario: Migration runs on existing SaaS database
- **WHEN** a deployment with this feature starts against a database containing pre-feature jobs and validated setups
- **THEN** the additive migration retains every existing row and the old resources remain readable with a deterministic default training readiness

### Requirement: Preparation uniqueness and quota decisions are atomic
The persistence layer SHALL enforce at most one non-terminal preparation per setup/fingerprint and SHALL perform preparation/training concurrency and idempotency reservations transactionally before the orchestrator creates a remote resource.

#### Scenario: Two workers reserve the same preparation
- **WHEN** concurrent API handlers attempt to create a preparation for one setup/fingerprint
- **THEN** exactly one durable reservation succeeds and the other returns the existing attempt without a second remote create

#### Scenario: Remote creation fails after reservation
- **WHEN** a reservation succeeds but remote submission fails terminally
- **THEN** the record becomes failed with a sanitized submission phase and no permanent quota slot remains occupied

