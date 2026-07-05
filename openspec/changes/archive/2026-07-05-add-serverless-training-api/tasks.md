## 1. Preset catalog

- [x] 1.1 Add `configs/training_presets.yaml` defining `halfcheetah-demo`, `ant-demo`, `ant-quality`, and feature-flagged `go1-mjx-demo`, each pinning backend/environment/algorithm/training budget/limits and declaring allowed safe params with bounds
- [x] 1.2 Implement `api/presets.py`: load and validate the catalog at startup (clear error on malformed/duplicate/missing presets), with a feature flag for `go1-mjx-demo`
- [x] 1.3 Implement preset resolution to an existing `RunConfig` (applying validated safe-param overrides and enforcing max step/duration limits)
- [x] 1.4 Add tests for catalog loading, allowlist enforcement, safe-param bounds, feature-flag gating, and resolution to `RunConfig`

## 2. Run state and artifacts in storage

- [x] 2.1 Define the per-run object-storage layout helper (metadata/checkpoints/tensorboard/videos/report) over `ArtifactStore`, reusing run-id/prefix/path validation
- [x] 2.2 Add a status writer that creates/updates `metadata/status.json` with status, `updated_at`, and a progress summary, plus `metadata/request.json`
- [x] 2.3 Add an `report/artifacts.json` manifest writer mapping logical artifact names to object keys
- [x] 2.4 Wire status transitions (`queued→starting→training→rendering→evaluating→completed`/`failed`) and manifest writing into the SB3/MJX training entrypoints
- [x] 2.5 Add tests for status lifecycle transitions, failure recording, and manifest contents

## 3. Orchestration backends

- [x] 3.1 Define the `OrchestrationBackend` protocol (launch given `run_id` + resolved config; report success/failure) in `api/orchestration.py`
- [x] 3.2 Implement `MockBackend`: simulate the full lifecycle, write `status.json` transitions and placeholder artifacts + manifest, no Nebius/GPU required
- [x] 3.3 Implement `NebiusBackend`: invoke `jobs/submit.sh` with `RUN_ID`, resolved `CONFIG`, backend, and limit-derived `TIMEOUT`; record the job handle; mark `failed` on submission error
- [x] 3.4 Ensure backends receive only `run_id` + catalog-resolved config (no user images/commands/env IDs/code), with run-id/limit validation before submission
- [x] 3.5 Add tests for backend selection, mock end-to-end run, and Nebius submission via `DRY_RUN`

## 4. HTTP API

- [x] 4.1 Add FastAPI app factory (`api/app.py`) and Pydantic models (`api/models.py`); select backend via `SIM2POLICY_API_BACKEND` (default `mock`)
- [x] 4.2 Implement `GET /health` (always open) reporting status and active backend mode
- [x] 4.3 Implement `GET /training-options` returning only allowlisted (enabled) presets with descriptions and safe-param ranges
- [x] 4.4 Implement `POST /train`: validate preset + safe params, generate safe `run_id`, persist `request.json`/`status.json=queued`, trigger backend, return `{run_id,status,status_url}`; reject unknown presets, extra/executable fields, and out-of-range params
- [x] 4.5 Implement `GET /runs/{run_id}` reading `status.json` from storage (404 on unknown, reject unsafe run ids)
- [x] 4.6 Implement `GET /runs/{run_id}/artifacts` building responses from `artifacts.json` with presigned (S3) or local URLs scoped to the run prefix; tolerate partial/incomplete runs
- [x] 4.7 Add the optional demo-token auth dependency (configurable, off by default, `/health` exempt)
- [x] 4.8 Add API tests covering each endpoint, validation/rejection paths, and a full mock-backed run-to-artifacts flow

## 5. Dependencies, docs, and wiring

- [x] 5.1 Add FastAPI/uvicorn (and presigned-URL support) as API-only runtime dependencies in `pyproject.toml`; add a `sim2policy-api` entrypoint and/or Make target
- [x] 5.2 Update `README.md` to document both modes: hosted API demo mode and bring-your-own-Nebius template mode, including running the API locally with the mock backend
- [x] 5.3 Add API/demo usage docs (endpoint reference, example requests/responses, security notes and limits) under `docs/`
- [x] 5.4 (Optional) Add a minimal static demo page that lists presets, starts a run, and shows the progression video and metrics
- [x] 5.5 Run lint/type/test suite and verify the full `POST /train` → status → artifacts flow against the mock backend
