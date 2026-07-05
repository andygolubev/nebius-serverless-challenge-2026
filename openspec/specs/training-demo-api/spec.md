# training-demo-api Specification

## Purpose
TBD - created by archiving change add-serverless-training-api. Update Purpose after archive.
## Requirements
### Requirement: Service health endpoint

The API SHALL expose `GET /health` that returns HTTP 200 and a JSON body reporting service health without requiring authentication.

#### Scenario: Health check succeeds

- **WHEN** a client sends `GET /health`
- **THEN** the API responds with HTTP 200 and a JSON body of `{ "status": "ok" }`

#### Scenario: Health check reflects backend mode

- **WHEN** a client sends `GET /health` while the orchestration backend is `mock`
- **THEN** the response indicates the active backend mode (e.g. `"backend": "mock"`) so operators can confirm whether real jobs will be launched

### Requirement: List available training options

The API SHALL expose `GET /training-options` that returns only allowlisted presets loaded from the preset catalog, never arbitrary or user-defined options.

#### Scenario: Returns allowlisted presets

- **WHEN** a client sends `GET /training-options`
- **THEN** the API responds with HTTP 200 and a list of presets, each including its name, backend, environment, human-readable description, and any safe tunable parameters with their allowed ranges

#### Scenario: Feature-flagged presets are hidden when disabled

- **WHEN** the `go1-mjx-demo` preset is feature-flagged off
- **THEN** `GET /training-options` does not include it in the returned list

### Requirement: Start a training run

The API SHALL expose `POST /train` that accepts a JSON body containing a `preset` and optional safe parameters (e.g. `seed`, `render_progress_video`), validates them, generates a safe `run_id`, persists run metadata, triggers the orchestration backend, and returns the new run handle.

#### Scenario: Valid request starts a run

- **WHEN** a client sends `POST /train` with `{ "preset": "ant-demo", "seed": 42, "render_progress_video": true }`
- **THEN** the API generates a `run_id` of the form `<preset>-<UTC-timestamp>-<random-suffix>`, persists the request and an initial `status.json` with status `queued`, triggers the orchestration backend, and responds with HTTP 202 and `{ "run_id", "status": "queued", "status_url" }`

#### Scenario: Unknown preset is rejected

- **WHEN** a client sends `POST /train` with a `preset` not present in the allowlist
- **THEN** the API responds with HTTP 422 (or 400) and an error, and does not create a run or trigger any job

#### Scenario: Arbitrary code or environment fields are rejected

- **WHEN** a client sends `POST /train` with extra fields such as an environment ID, image reference, command, code path, or reward function
- **THEN** the API rejects the request and does not pass any user-supplied executable input to the orchestration backend

#### Scenario: Out-of-range safe parameter is rejected

- **WHEN** a client sends `POST /train` with a safe parameter outside the preset's allowed range (e.g. a `seed` outside the permitted bounds)
- **THEN** the API responds with a validation error and does not create a run

### Requirement: Get run status

The API SHALL expose `GET /runs/{run_id}` that returns the run's current status and progress summary derived from stored run metadata.

#### Scenario: Returns status from stored metadata

- **WHEN** a client sends `GET /runs/{run_id}` for an existing run
- **THEN** the API responds with HTTP 200 and `{ run_id, preset, status, created_at, updated_at, progress }`, where `status` reflects the latest persisted `status.json` and `progress` includes phase, latest checkpoint, and latest mean reward when available

#### Scenario: Unknown run id returns not found

- **WHEN** a client sends `GET /runs/{run_id}` for a `run_id` with no stored metadata
- **THEN** the API responds with HTTP 404

#### Scenario: Run id is validated before lookup

- **WHEN** a client requests a `run_id` containing path-traversal or otherwise unsafe characters
- **THEN** the API rejects it as invalid without performing a storage lookup

### Requirement: List run artifacts

The API SHALL expose `GET /runs/{run_id}/artifacts` that returns downloadable URLs for the run's artifacts once they exist, sourced from the run's artifact manifest.

#### Scenario: Returns artifact URLs after completion

- **WHEN** a client sends `GET /runs/{run_id}/artifacts` for a `completed` run
- **THEN** the API responds with HTTP 200 and an `artifacts` object containing URLs for available items such as `final_policy`, `metrics_json`, `report_md`, `video_untrained`, `video_mid`, `video_final`, and `progression_montage`

#### Scenario: Artifacts requested before completion

- **WHEN** a client sends `GET /runs/{run_id}/artifacts` for a run that has not yet produced artifacts
- **THEN** the API responds with the current status and only the artifacts that already exist (which may be an empty set), rather than failing

#### Scenario: URLs are scoped to the run prefix

- **WHEN** the API returns artifact URLs
- **THEN** every URL resolves under the run's own object-storage prefix and is either a presigned URL or a documented public URL, and no URL is constructed from client-supplied paths

### Requirement: Demo safety controls

The API SHALL enforce demo-grade safety controls: a configurable simple demo-token authentication placeholder, per-run limits, and rejection of any input that is not an allowlisted preset or a bounded safe parameter.

#### Scenario: Demo token gate when enabled

- **WHEN** demo-token auth is enabled and a client calls a protected endpoint without a valid token
- **THEN** the API responds with HTTP 401, and `GET /health` remains accessible without a token

#### Scenario: Per-run limits applied from preset

- **WHEN** a run is started
- **THEN** the resolved job configuration applies the preset's bounded limits (max training steps and max job duration) and the client cannot exceed them through request parameters

