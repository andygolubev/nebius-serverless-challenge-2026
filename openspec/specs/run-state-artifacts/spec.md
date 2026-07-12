# run-state-artifacts Specification

## Purpose
Keep all durable run state in object storage under one validated per-run prefix — a fixed layout
for metadata, checkpoints, logs, videos, and reports; a `status.json` advanced through the
canonical lifecycle `queued → starting → training → rendering → evaluating → completed/failed`;
and an artifact manifest from which APIs build presigned, run-scoped URLs — so API instances stay
stateless.

## Requirements
### Requirement: Per-run object-storage layout

Each run SHALL persist all durable state under a single, stable object-storage prefix `<bucket>/<storage-prefix>/<run_id>/`, using a fixed layout for metadata, checkpoints, TensorBoard logs, videos, and reports. No path component SHALL be derived from raw client input.

#### Scenario: Run prefix layout

- **WHEN** a run produces durable state
- **THEN** it is written under `<run_id>/` using the layout: `metadata/status.json`, `metadata/request.json`, `checkpoints/`, `tensorboard/`, `videos/{untrained,mid,final,progression_montage}.mp4`, `report/metrics.json`, `report/report.md`, and `report/artifacts.json`

#### Scenario: Paths are validated

- **WHEN** any artifact key is constructed
- **THEN** the `run_id` and relative path are validated against safe patterns, rejecting empty, absolute, or traversal (`..`) components

### Requirement: Run status lifecycle

The training job (or mock backend) SHALL maintain `metadata/status.json` and advance it through the lifecycle `queued → starting → training → rendering → evaluating → completed`, or to `failed` from any phase on error. Each update SHALL include a timestamp and a progress summary.

#### Scenario: Status advances through phases

- **WHEN** a run executes successfully
- **THEN** `status.json` is updated at each phase transition with `status`, `updated_at`, and a `progress` object (phase, latest checkpoint, latest mean reward when available), ending at `completed`

#### Scenario: Failure is recorded

- **WHEN** a run encounters an unrecoverable error in any phase
- **THEN** `status.json` is set to `failed` with an error summary and a final `updated_at`

#### Scenario: API derives status from storage

- **WHEN** the API serves `GET /runs/{run_id}`
- **THEN** it reads and returns the latest persisted `status.json` rather than holding run state only in memory

### Requirement: Artifact manifest

On completion, the run SHALL write `report/artifacts.json` listing the produced artifacts and their object keys. The API SHALL build artifact response URLs from this manifest.

#### Scenario: Manifest lists produced artifacts

- **WHEN** a run completes
- **THEN** `artifacts.json` maps logical names (`final_policy`, `metrics_json`, `report_md`, `video_untrained`, `video_mid`, `video_final`, `progression_montage`) to their object keys for items that were produced

#### Scenario: Signed URLs are generated on demand

- **WHEN** the API responds to `GET /runs/{run_id}/artifacts` for a run on S3-compatible storage
- **THEN** it returns presigned (time-limited) URLs derived from the manifest's object keys, scoped to the run prefix

