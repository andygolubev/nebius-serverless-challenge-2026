# SaaS artifact lazy recovery

## Why

Completed MJX training-only jobs are permanently stuck at `409 artifacts not ready`: the
backend reads `report/artifacts.json` from S3 exactly once at job completion
(`orchestration.py:_complete`), but training-only runs publish that manifest only later,
via the separate finalization pipeline. Any job whose manifest appears after completion —
including the real run `9b32bd6038ec4c34a1ec4681f661bc84` (102.4M steps, checkpoints in S3,
no `report/*` keys) — can never serve artifacts, even after finalization succeeds.

## What Changes

- `GET /jobs/{job_id}/artifacts` gains a lazy S3 fallback: when the store has no cached
  manifest and the job is `completed`, the backend re-reads
  `sim2policy/<run-id>/report/artifacts.json` from S3; on success it caches the manifest
  in SQLite and returns it, otherwise it keeps returning `409`.
- The `S3ArtifactReader` already built in `build_backend` is exposed so the API layer can
  reuse it (mock backend behavior unchanged).
- Operational (not code): run the finalization pipeline for run
  `9b32bd6038ec4c34a1ec4681f661bc84` as a Nebius Serverless AI job on
  `gpu-l40s-a` / `1gpu-8vcpu-32gb` to publish its manifest, videos, and metrics.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `saas-artifact-access`: the "Artifacts not yet written" behavior changes — a `completed`
  job with no cached manifest triggers an on-demand S3 manifest read (with caching) before
  the API falls back to `409 artifacts not ready`.

## Impact

- Code: `saas/backend/app/main.py` (`get_artifacts`), `saas/backend/app/orchestration.py`
  (expose artifact reader on `NebiusBackend` / `build_backend`), backend unit tests.
- API: `GET /jobs/{job_id}/artifacts` may now return `200` for jobs finalized after
  completion; no schema changes, no breaking changes.
- Operations: one L40S finalize job (~15–25 min, <$1) for the stuck run; one SaaS image
  deploy through the existing GitOps pipeline.
