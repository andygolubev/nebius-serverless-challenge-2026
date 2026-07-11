# saas-data-persistence Specification

## Purpose
Ensure the SaaS backend persists tenant state across process restarts and pod redeploys using durable
storage, while remaining configurable for local development and cluster deployments.

## Requirements

### Requirement: Tenant data persists across restarts
The SaaS backend SHALL store users, sessions, jobs, and artifact manifests in a SQLite database on
durable storage so that this state survives backend process restarts and pod redeploys. Pending
one-time login codes and rate-limit windows MAY remain in process memory.

#### Scenario: Jobs survive a restart
- **WHEN** a tenant has submitted jobs and the backend process restarts
- **THEN** listing jobs with a valid session returns the same jobs with their last recorded state

#### Scenario: Artifacts survive a restart
- **WHEN** a job completed with an artifact manifest before a backend restart
- **THEN** requesting that job's artifacts after the restart returns the same manifest

#### Scenario: Tenant isolation is preserved
- **WHEN** persisted jobs belong to multiple tenants
- **THEN** each session can only read jobs and artifacts belonging to its own tenant, exactly as
  before persistence

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
