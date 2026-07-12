# Design: SaaS artifact lazy recovery

## Context

`GET /jobs/{job_id}/artifacts` serves an `ArtifactManifest` cached in SQLite. The cache is
populated exactly once, in `NebiusBackend._complete()` (`saas/backend/app/orchestration.py:232-242`),
by reading `sim2policy/<run-id>/report/artifacts.json` from S3 at the moment the Nebius job
reaches a terminal-success state. MJX training-only runs never write that manifest —
`train_mjx.py` only writes it when `discover_artifacts()` finds files matching the fixed
`ARTIFACT_KEYS` names (`checkpoints/final.zip`, `report/metrics.json`, videos), all of which
are produced by the separate finalization pipeline (`sim2policy/src/sim2policy/finalize.py`).
Result: a job completed before finalization is permanently `409 artifacts not ready`, even
after finalization later publishes the manifest. Run `9b32bd6038ec4c34a1ec4681f661bc84` is
in this state today (170 S3 objects, zero `report/*` keys).

## Goals / Non-Goals

**Goals:**
- A `completed` job whose manifest appears in S3 *after* completion becomes servable without
  redeploys or manual DB edits.
- Keep the 409 contract for genuinely-not-ready runs.
- No behavior change for the mock backend or for jobs that already have a cached manifest.

**Non-Goals:**
- Changing the trainer or finalization pipeline (manifest publication stays finalize's job).
- Automatic finalization of training-only runs.
- Retry loops or background pollers in the SaaS backend.

## Decisions

1. **Lazy read-through on request, not a background retry.** In `get_artifacts`
   (`saas/backend/app/main.py`), when `store.get_artifacts()` misses and the job status is
   `completed`, call the existing `S3ArtifactReader.read_manifest(job_id, job_id)`; on
   success, `store.set_artifacts()` then return. One S3 GET per miss-request is cheap,
   self-healing, and avoids new threads/state. Alternative rejected: periodic re-poll in
   `_complete` — adds lifetime/threading complexity and doesn't help jobs that completed
   before a restart.
2. **Expose the reader via the backend.** `build_backend("nebius")` already constructs the
   `S3ArtifactReader`; attach it as an attribute (e.g. `backend.artifact_reader`, `None` on
   `MockBackend`). `main.py` uses it when present. Alternative rejected: constructing a
   second reader in `main.py` — duplicates settings/boto3 wiring.
3. **Gate on `completed` status.** Avoids S3 reads for running/failed jobs and preserves the
   existing "mid-run 409" semantics.
4. **Swallow S3 errors into 409.** A transient S3 failure during the lazy read logs a warning
   and returns 409 (same as today), never a 500.

## Risks / Trade-offs

- [S3 latency on every miss for completed-but-unfinalized jobs] → single GET per request,
  bounded by boto3 timeouts; acceptable for the UI's polling cadence.
- [Stale cache: manifest re-published after first cache] → out of scope; manifest content is
  effectively immutable per run.
- [Ordering: `set_artifacts` racing `_complete`'s own write] → both writes are
  `INSERT OR REPLACE` of identical S3-derived content; last-writer-wins is harmless.

## Migration Plan

1. Land code + tests, build/push SaaS image, deploy via existing GitOps flow (watch the
   ArgoCD `kustomize.images` override gotcha).
2. Run the finalize job for `9b32bd6038ec4c34a1ec4681f661bc84` on `gpu-l40s-a` /
   `1gpu-8vcpu-32gb` (module `sim2policy.finalize`, config `configs/go1_mjx.yaml`, same
   `storage.*` overrides and MysteryBox secret wiring as training, ~1h timeout).
3. Rollback: revert image tag; endpoint returns to old (409-forever) behavior with no data
   migration needed.

## Open Questions

- None blocking. (Optional follow-up: teach `train_mjx` to publish a checkpoint-only
  manifest so training-only runs are never 409 — deliberately excluded here.)
