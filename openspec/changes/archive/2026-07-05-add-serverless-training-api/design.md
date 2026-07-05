## Context

Sim2Policy already has a working training pipeline: configurable SB3/MJX PPO backends, an `ArtifactStore` over local or S3-compatible storage with a validated per-run prefix (`<prefix>/<run_id>/`), deterministic rendering, evaluation/reporting, and a Nebius job-submission wrapper (`jobs/submit.sh`) driving `nebius ai job create`. Run IDs and storage prefixes are already validated by safe regex patterns in `config.py` (`RUN_ID_PATTERN`, `SAFE_PREFIX_PATTERN`), and `ArtifactStore.key_for` already rejects traversal.

What is missing is a *front door*. To run the pipeline today you clone the repo, build the container, and submit a job by hand. This change adds a thin hosted HTTP layer so demo users can start a controlled run and fetch artifacts with a few calls, while the training implementation stays entirely project-controlled. The API is additive and reuses the existing storage layout, run-config schema, and job wrapper rather than duplicating them.

Constraints: this is a demo phase. No user-supplied code/images/environments/reward functions. The same repo must remain usable as a bring-your-own-Nebius template, so the API must degrade to a local/mock mode with no Nebius credentials.

## Goals / Non-Goals

**Goals:**

- A small FastAPI app exposing `GET /health`, `GET /training-options`, `POST /train`, `GET /runs/{run_id}`, `GET /runs/{run_id}/artifacts`.
- Strict allowlist validation: only catalog presets and bounded safe parameters are accepted.
- Pluggable orchestration backend with two implementations: `nebius` (reuses `jobs/submit.sh`) and `mock` (no GPU/credentials).
- API reads run state from object storage (`status.json` / `artifacts.json`), not from in-process memory, so it works across stateless/serverless instances.
- Reuse existing `RunConfig`, `ArtifactStore`, and run-id/prefix validation.

**Non-Goals:**

- No custom environments, reward functions, policy architectures, or user Docker images.
- No production auth, billing, multi-tenancy, quotas, or model registry.
- No required web UI (a minimal static demo page is optional).
- No change to the training/render/evaluate/report requirements themselves.

## Decisions

### 1. FastAPI app under `sim2policy/src/sim2policy/api/`

A FastAPI app (run by uvicorn locally, deployable as a serverless endpoint) gives Pydantic request validation, automatic OpenAPI docs, and an easy mock mode — all valuable for a demo surface. Layout:

- `api/app.py` — app factory and route wiring
- `api/models.py` — Pydantic request/response models
- `api/presets.py` — loads/validates `configs/training_presets.yaml`, resolves a preset (+ safe params) into a `RunConfig`
- `api/orchestration.py` — `OrchestrationBackend` protocol + `NebiusBackend` and `MockBackend`
- `api/state.py` — reads `status.json`/`artifacts.json` from `ArtifactStore`, builds presigned URLs

_Alternative considered:_ a bare ASGI/Flask service — rejected; FastAPI's validation and schema generation directly serve the "reject anything not allowlisted" requirement with less code.

### 2. Presets as a declarative allowlist (`configs/training_presets.yaml`)

Each preset entry pins backend/environment/algorithm/training budget/limits and declares which safe params are overridable (e.g. `seed`, `render_progress_video`) with bounds. The preset resolver returns a fully-formed `RunConfig` — the same dataclass the training entrypoints already consume — so the API never constructs ad-hoc configs and the existing per-preset YAMLs (`ant_sb3.yaml`, etc.) remain the source of training hyperparameters that presets reference or mirror.

_Alternative considered:_ hardcoding presets in Python — rejected; a config file keeps the allowlist auditable and easy to feature-flag (`go1-mjx-demo`).

### 3. Storage is the source of truth for run state

The training job writes `metadata/request.json` and a continuously-updated `metadata/status.json`, and on completion `report/artifacts.json`. The API derives all status/artifact responses by reading these objects through `ArtifactStore`. This keeps the API stateless and serverless-friendly and means a real Nebius job and a mock run are observed identically. The training entrypoints gain a small status-writer responsibility (phase transitions + progress summary).

_Alternative considered:_ a separate metadata database — rejected for this phase; object storage already holds durable run state and avoids a new stateful dependency. A DB is listed as a future option if run listing/search is needed.

### 4. Orchestration backend abstraction

`POST /train` validates → generates `run_id` (`<preset>-<UTCYYYYMMDD>-<rand>` matching `RUN_ID_PATTERN`) → writes initial `request.json` + `status.json=queued` → calls the selected backend. `NebiusBackend` shells out to the existing `jobs/submit.sh` (env-driven, secret-selector based) passing `RUN_ID`, resolved `CONFIG`, backend, and limit-derived `TIMEOUT`. `MockBackend` spawns a background task that walks `status.json` through the lifecycle and drops placeholder artifacts. Backend is chosen by env/config (`SIM2POLICY_API_BACKEND=mock|nebius`), surfaced in `/health`.

_Alternative considered:_ calling the Nebius API/SDK directly from Python — deferred; reusing `jobs/submit.sh` keeps one audited submission path and its secret handling.

### 5. Artifact URLs via presigned S3 GETs

`GET /runs/{run_id}/artifacts` reads `artifacts.json`, then for S3 mode generates time-limited presigned URLs from the manifest's object keys (scoped to the run prefix); for local mode it returns local paths/relative refs. URLs are never built from client input.

_Alternative considered:_ public-read bucket URLs — left as a documented option but presigned is the safer default for a demo.

### 6. Demo auth as a thin, optional token gate

A single configurable demo token checked via a dependency on the mutating/listing endpoints (`/health` always open). It is explicitly a placeholder, easy to replace with real auth later.

## Risks / Trade-offs

- **Eventually-consistent / polling status** → The API reads `status.json` each request; a brief lag between job progress and visible status is acceptable for a demo. Mitigation: training writes status at every phase transition and on a periodic cadence.
- **Cost/abuse from open demo runs** → Presets carry max step/duration limits and the API refuses to exceed them; a demo token and (future) rate limiting bound usage. Mitigation: keep default presets short and document operator-side Nebius quotas.
- **`jobs/submit.sh` shell coupling** → Driving submission via a shell script from a web process risks quoting/secret issues. Mitigation: pass inputs via env vars (already the script's contract), reuse its `RUN_ID`/duration validation, never pass secrets on the command line, and keep `DRY_RUN` support for tests.
- **MJX preset readiness** → `go1-mjx-demo` may be unstable. Mitigation: feature-flag it off by default; hidden from `/training-options` and rejected by `POST /train` when disabled.
- **Stale artifact manifest if a job dies mid-run** → `GET /artifacts` returns only artifacts already present plus current status, never erroring on partial runs. Mitigation: failure path writes `status=failed`.

## Migration Plan

1. Land `configs/training_presets.yaml` + preset loader/resolver and tests (no behavior change yet).
2. Add status/artifact-manifest writing to the training entrypoints (backward compatible — extra files under the run prefix).
3. Add the FastAPI app with the `mock` backend as default; ship API tests that need no Nebius/GPU.
4. Wire `NebiusBackend` to `jobs/submit.sh` behind `SIM2POLICY_API_BACKEND=nebius`; validate with `DRY_RUN` then a real short `ant-demo`/`halfcheetah-demo` run.
5. Update README to document hosted-demo mode vs. bring-your-own-Nebius template mode; optionally add a minimal static demo page.

Rollback: the API package and presets file are isolated; disabling/removing the API leaves the existing template pipeline fully functional.

## Open Questions

- Hosting target for the endpoint — Nebius serverless endpoint vs. a long-running small FastAPI service. (Does not block the API contract.)
- Presigned URL TTL default and whether local mode should serve files over HTTP for the demo page.
- Whether to add a lightweight `GET /runs` listing in this phase or defer until a metadata store exists.
