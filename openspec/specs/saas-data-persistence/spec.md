# saas-data-persistence Specification

## Purpose
Ensure the SaaS backend persists tenant state across process restarts and pod redeploys using durable
storage, while remaining configurable for local development and cluster deployments.

## Requirements

### Requirement: Tenant data persists across restarts
The SaaS backend SHALL store users, sessions, jobs, artifact manifests, bounded robot XML and
metadata, and normalized robot environment drafts in a SQLite database on durable storage so that
this state survives backend process restarts and pod redeploys. Pending one-time login codes and
rate-limit windows MAY remain in process memory.

#### Scenario: Jobs survive a restart
- **WHEN** a tenant has submitted jobs and the backend process restarts
- **THEN** listing jobs with a valid session returns the same jobs with their last recorded state

#### Scenario: Artifacts survive a restart
- **WHEN** a job completed with an artifact manifest before a backend restart
- **THEN** requesting that job's artifacts after the restart returns the same manifest

#### Scenario: Robot assets and drafts survive a restart
- **WHEN** a tenant uploaded a valid robot and saved an environment draft before a backend restart
- **THEN** listing robots and drafts with the same tenant session returns the same immutable
  content, metadata, and readiness state

#### Scenario: Tenant isolation is preserved
- **WHEN** persisted jobs, robot assets, or environment drafts belong to multiple tenants
- **THEN** each session can only read state belonging to its own tenant, exactly as before
  persistence

### Requirement: Bounded custom-asset persistence quotas
The persistent store SHALL enforce at most 20 active custom robot versions and 50 active
environment drafts per tenant, in addition to the 1 MiB per-robot upload limit, before writing a
new row.

#### Scenario: Robot quota is exhausted
- **WHEN** a tenant with 20 active custom robot versions attempts to add a distinct robot
- **THEN** the API rejects the upload with a quota diagnostic and does not modify existing rows

#### Scenario: Draft quota is exhausted
- **WHEN** a tenant with 50 active environment drafts attempts to save another draft
- **THEN** the API rejects the request with a quota diagnostic and preserves existing drafts

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

### Requirement: Database location is configurable
The backend SHALL read the SQLite database file path from the `SAAS_DB_PATH` environment variable
and SHALL create the database schema automatically at startup if it does not exist. When
`SAAS_DB_PATH` is unset, the backend SHALL default to a local file path so development and tests
run without any volume configured.

#### Scenario: Fresh volume initialization
- **WHEN** the backend starts with `SAAS_DB_PATH` pointing at a path with no existing database
- **THEN** it creates the database and schema and serves requests normally

#### Scenario: Local development without configuration
- **WHEN** the backend starts with `SAAS_DB_PATH` unset
- **THEN** it runs against a default local database file without requiring a mounted volume

### Requirement: Durable volume in the cluster deployment
The SaaS Kubernetes deployment SHALL mount a PersistentVolumeClaim for the SQLite database and
SHALL use the `Recreate` deployment strategy so the ReadWriteOnce volume is released before a
replacement pod starts. The PVC SHALL be managed in the GitOps manifests alongside the existing
SaaS deployment.

#### Scenario: Redeploy retains data
- **WHEN** ArgoCD rolls out a new SaaS image
- **THEN** the replacement pod mounts the same volume and serves the previously persisted users,
  sessions, jobs, and artifacts

#### Scenario: Rollout does not deadlock on the volume
- **WHEN** a new pod replaces the old one during a sync
- **THEN** the old pod terminates before the new pod attaches the volume, and the rollout
  completes without manual intervention
