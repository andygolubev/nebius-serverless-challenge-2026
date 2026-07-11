## MODIFIED Requirements

### Requirement: Nebius job orchestration

The Nebius backend SHALL launch the run as a Nebius Serverless AI Job using the existing job-submission path (`jobs/submit.sh` / `nebius ai job create`), passing the run's preset config and `run_id`, and applying the preset's duration and step limits. Each submission SHALL use the runtime image and compute shape (platform and preset) declared by the catalog job spec for the run's environment/algorithm combination: SB3-backed specs use the configured SB3 runtime image, and MJX-backed specs use the configured MJX runtime image. The backend's settings contract SHALL require both runtime image references at startup and SHALL fail readiness when either is missing.

#### Scenario: Launches a Nebius job in production mode

- **WHEN** `POST /train` is handled with the Nebius backend and valid credentials
- **THEN** the backend submits a Nebius Serverless AI Job that runs the existing training entrypoint (`sim2policy.train_sb3`/`train_mjx`) for the resolved preset with the run's `run_id`, and records the job handle in run metadata

#### Scenario: MJX spec runs on the MJX runtime image

- **WHEN** the backend builds the submission for an MJX-backed job spec (e.g. `go1`/`ppo-mjx`)
- **THEN** the submission's image is the configured MJX runtime image and its platform/preset are the shape declared by that job spec

#### Scenario: SB3 spec runs on the SB3 runtime image and right-sized hardware

- **WHEN** the backend builds the submission for an SB3-backed job spec
- **THEN** the submission's image is the configured SB3 runtime image and its platform/preset are the SB3 spec's declared shape, which is not required to match the MJX shape

#### Scenario: Missing MJX image configuration fails startup

- **WHEN** the nebius backend is selected but the MJX runtime image variable is unset
- **THEN** settings validation fails at startup and the pod does not become ready, and no job submission is attempted

#### Scenario: Launch failure marks the run failed

- **WHEN** the Nebius job submission fails
- **THEN** the run's `status.json` is set to `failed` with an error summary, and the API reports the failure on subsequent status requests

#### Scenario: Run id and limits are validated before submission

- **WHEN** the backend builds the submission
- **THEN** it validates the `run_id` against the safe pattern and enforces the preset's max step/duration limits, refusing to submit otherwise
