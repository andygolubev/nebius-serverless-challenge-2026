# training-job-orchestration Specification

## Purpose
TBD - created by archiving change add-serverless-training-api. Update Purpose after archive.
## Requirements
### Requirement: Orchestration backend abstraction

The system SHALL define an orchestration backend interface that, given a validated `run_id` and a resolved preset configuration, launches a training run and reports launch success or failure. The API SHALL select the backend (`nebius` or `mock`) by configuration and SHALL NOT perform training itself.

#### Scenario: Backend selected by configuration

- **WHEN** the service starts with the orchestration backend set to `mock`
- **THEN** `POST /train` uses the mock backend, and no Nebius CLI call or GPU job is invoked

#### Scenario: Only safe inputs reach the backend

- **WHEN** the API invokes any orchestration backend
- **THEN** it passes only the generated `run_id` and the catalog-resolved configuration, never user-supplied images, commands, environment IDs, or code

### Requirement: Nebius job orchestration

The Nebius backend SHALL launch the run as a Nebius Serverless AI Job using the existing job-submission path (`jobs/submit.sh` / `nebius ai job create`), passing the run's preset config and `run_id`, and applying the preset's duration and step limits.

#### Scenario: Launches a Nebius job in production mode

- **WHEN** `POST /train` is handled with the Nebius backend and valid credentials
- **THEN** the backend submits a Nebius Serverless AI Job that runs the existing training entrypoint (`sim2policy.train_sb3`/`train_mjx`) for the resolved preset with the run's `run_id`, and records the job handle in run metadata

#### Scenario: Launch failure marks the run failed

- **WHEN** the Nebius job submission fails
- **THEN** the run's `status.json` is set to `failed` with an error summary, and the API reports the failure on subsequent status requests

#### Scenario: Run id and limits are validated before submission

- **WHEN** the backend builds the submission
- **THEN** it validates the `run_id` against the safe pattern and enforces the preset's max step/duration limits, refusing to submit otherwise

### Requirement: Mock orchestration backend

The system SHALL provide a mock backend that simulates a full run lifecycle and writes the same object-storage layout (status transitions and a minimal artifact manifest) so the entire API surface can be exercised locally without Nebius credentials or GPU.

#### Scenario: Mock run completes without Nebius

- **WHEN** `POST /train` is handled with the mock backend
- **THEN** a run is created and its `status.json` advances through the lifecycle to `completed`, writing placeholder artifacts and an `artifacts.json` manifest, with no Nebius credentials required

#### Scenario: Mock run is observable through the API

- **WHEN** a mock run is in progress or finished
- **THEN** `GET /runs/{run_id}` and `GET /runs/{run_id}/artifacts` return status and artifact links exactly as they would for a real run

