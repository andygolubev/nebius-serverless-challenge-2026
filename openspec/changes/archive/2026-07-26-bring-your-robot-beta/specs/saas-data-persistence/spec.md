## MODIFIED Requirements

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

## ADDED Requirements

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
