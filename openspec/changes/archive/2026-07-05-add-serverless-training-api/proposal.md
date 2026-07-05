## Why

Today, running a Sim2Policy training run requires cloning the repository, building a CUDA container, configuring object storage, and submitting a Nebius Serverless AI Job by hand. That is the right experience for the open-source "bring-your-own-Nebius" template, but it is too much friction for someone who just wants to *see* the project work — start a known-good robot training run and watch a policy progress from flailing to walking. We want a hosted demo service that turns that into three HTTP calls, while keeping the training implementation fully controlled by the project (no user-supplied code, environments, images, or reward functions in this phase).

## What Changes

- Add a hosted HTTP API layer (FastAPI/serverless endpoint) that lets demo users start **predefined** training runs and track them, without cloning the repo or owning Nebius infrastructure.
- Add endpoints: `GET /health`, `GET /training-options`, `POST /train`, `GET /runs/{run_id}`, and `GET /runs/{run_id}/artifacts`.
- Add an allowlisted preset catalog (`configs/training_presets.yaml`) exposing a small, controlled set of options: `halfcheetah-demo`, `ant-demo`, `ant-quality`, and an optional feature-flagged `go1-mjx-demo`.
- Add an orchestration layer that translates a validated `(preset, safe params)` request into a `run_id` and a Nebius Serverless AI Job invocation, reusing the existing `jobs/submit.sh` job-submission path.
- Add a **mock/dev backend** so the full API surface can run and be tested locally without Nebius credentials or GPU jobs.
- Define a per-run object-storage layout and a `status.json`-driven run-status lifecycle (`queued → starting → training → rendering → evaluating → completed`/`failed`) that the training job writes and the API reads.
- Add demo-grade safety controls: preset allowlisting, safe `run_id` generation, no arbitrary storage paths/env IDs/images, per-run limits (max steps/duration), and a documented simple demo-token auth placeholder.
- Update the README to document **two modes**: hosted API demo mode and bring-your-own-Nebius template mode.
- This is **additive**: the existing training/render/evaluate/report pipeline and template workflow are unchanged. The API is a thin layer in front of them.

## Capabilities

### New Capabilities

- `training-demo-api`: The hosted HTTP service surface — health, training-options, train, run-status, and artifact-listing endpoints; request validation against the preset allowlist; safe `run_id` generation; demo auth placeholder and per-run limits.
- `training-presets`: The allowlisted, declarative catalog of demo training options (`configs/training_presets.yaml`) mapping a preset name to a fixed backend/environment/algorithm/limits, and the rule that only allowlisted presets are accepted.
- `training-job-orchestration`: Translating a validated request into a launched Nebius Serverless AI Job (passing only `run_id` and a resolved preset config), plus a mock backend that simulates a run end-to-end without Nebius/GPU.
- `run-state-artifacts`: The per-run object-storage layout, the `status.json` run-status lifecycle the training job maintains, the `artifacts.json` manifest, and how the API derives status and downloadable/signed artifact URLs from stored metadata.

### Modified Capabilities

None. The existing capabilities (`policy-training-backends`, `durable-run-artifacts`, `rollout-media`, `policy-evaluation-reporting`, `serverless-template-workflow`) are reused as-is; this change wraps them rather than altering their requirements.

## Impact

- Adds a new API package (e.g. `sim2policy/src/sim2policy/api/`) with the FastAPI app, request/response models, preset loader, orchestration backends (Nebius + mock), and a metadata/status reader over object storage.
- Adds `configs/training_presets.yaml` and corresponding tests for the API, preset validation, orchestration, and storage-layout reads.
- Reuses `jobs/submit.sh`, the `ArtifactStore`/storage layout, and the existing `train_sb3`/`train_mjx` entrypoints; the training job gains responsibility for writing `metadata/status.json` and `report/artifacts.json` to the run prefix.
- Introduces FastAPI/uvicorn (and presigned-URL support via boto3) as new runtime dependencies for the API surface only; the training container is unaffected.
- Updates `README.md` and adds API/demo documentation. No production auth, billing, multi-tenancy, or custom-upload support is introduced in this phase.
