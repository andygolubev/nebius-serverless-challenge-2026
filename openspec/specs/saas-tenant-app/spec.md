# saas-tenant-app Specification

## Purpose
Provide the tenant-facing SaaS application: a web UI and HTTP API for submitting training jobs,
tracking their lifecycle, and retrieving results — with orchestration isolated behind a pluggable
backend (mock first) and strict per-tenant isolation of jobs and artifacts.

## Requirements

### Requirement: Tenant can submit and track jobs
The SaaS app SHALL let a tenant submit a training job and view its status and results through a web
UI backed by an HTTP API. For this change the job orchestration backend MAY be a mock that simulates
the job lifecycle; the API contract SHALL be identical to what a real backend will implement.

#### Scenario: Submit a job
- **WHEN** a tenant submits a job through the UI or `POST` to the job API
- **THEN** the app creates a job with a unique id in `queued`/`starting` state and returns that id

#### Scenario: Track job to completion
- **WHEN** a tenant polls a submitted job's status
- **THEN** the app reports lifecycle transitions through to a terminal `completed` or `failed` state

#### Scenario: Retrieve results
- **WHEN** a tenant requests the artifacts of a completed job
- **THEN** the app returns the result manifest (e.g. metrics, links to media) for that job

### Requirement: Pluggable orchestration backend
The SaaS backend SHALL isolate job orchestration behind an interface with at least a `mock`
implementation, so a real Nebius Serverless orchestrator can be added later without changing the
tenant-facing API or UI.

#### Scenario: Mock backend drives the full lifecycle
- **WHEN** the app is configured with the mock orchestration backend
- **THEN** submitted jobs progress through the full status lifecycle and produce placeholder
  artifacts with no Nebius credentials or GPU required

#### Scenario: Backend is selected by configuration
- **WHEN** the orchestration backend is switched by configuration
- **THEN** the tenant-facing API request/response shapes remain unchanged

### Requirement: Tenant isolation of jobs and results
The app SHALL scope every job and its artifacts to the tenant that created it, so one tenant cannot
read or act on another tenant's jobs.

#### Scenario: Tenant sees only own jobs
- **WHEN** a tenant lists jobs or requests a job it does not own
- **THEN** the app returns only that tenant's jobs and denies access to jobs owned by others
