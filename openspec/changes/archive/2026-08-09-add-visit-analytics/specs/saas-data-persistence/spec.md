## MODIFIED Requirements

### Requirement: Tenant data persists across restarts
The SaaS backend SHALL store users, sessions, jobs, artifact manifests, bounded robot XML and
metadata, normalized robot environment drafts, and site visit analytics in a SQLite database on
durable storage so that this state survives backend process restarts and pod redeploys. Pending
one-time login codes and rate-limit windows MAY remain in process memory.

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

#### Scenario: Visit analytics survive a restart
- **WHEN** visits and page views were recorded before a backend restart
- **THEN** those rows, and any daily totals derived from them, remain present in the database after
  the restart

## ADDED Requirements

### Requirement: Analytics is the only bounded-retention state
Every persisted table other than the site visit analytics tables SHALL be retained indefinitely;
there is no delete path for tenant, job, artifact, or robot state. The visit, page-view, and
daily-totals tables are the sole exception: raw analytics rows SHALL be pruned on a fixed retention
window, and daily totals SHALL be retained indefinitely. Analytics rows SHALL NOT be tenant-scoped
and SHALL NOT reference tenant identity, since they describe anonymous public traffic.

#### Scenario: Analytics pruning is isolated
- **WHEN** the analytics retention task deletes expired rows
- **THEN** only analytics tables are affected and every tenant, job, artifact, and robot row is
  preserved

#### Scenario: Analytics carries no tenant identity
- **WHEN** an analytics row is written for a visitor who also holds a valid session
- **THEN** the row records no email, tenant id, or session token

#### Scenario: Analytics schema is added without disturbing existing data
- **WHEN** a database created by an earlier release is opened by the new backend
- **THEN** the analytics tables are created and all existing users, sessions, jobs, artifact
  manifests, robots, setups, preparation attempts, and training requests are preserved unchanged
