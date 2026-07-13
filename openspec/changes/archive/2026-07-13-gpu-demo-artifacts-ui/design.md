## Context

The production SaaS currently has one verified GPU-accelerated path: Go1 PPO through MJX/JAX on `gpu-h100-sxm` / `1gpu-16vcpu-200gb`. The catalog also exposes SB3 workloads that are primarily CPU-bound and Ant/MJX even though Ant/MJX has no production job spec. Live inspection showed a guaranteed Ant/MJX failure, an SB3 job stuck in `starting`, completed Go1 runs whose nested metrics render as `[object Object]`, and four real MP4 objects exposed as relative links rather than downloadable URLs.

Training jobs write durable run data to S3, while final evaluation/rendering may publish `report/artifacts.json` after the remote training job succeeds. The current poller marks a tenant job completed at remote success and then leaves the UI polling a 409 artifact endpoint indefinitely. Polling runs in daemon threads and does not resume persisted active jobs after process restart.

## Goals / Non-Goals

**Goals:**

- Offer at least three honest, bounded GPU-accelerated PPO demos at increasing sizes.
- Make every publicly selectable workload executable by construction.
- Model training, finalization, and artifact readiness truthfully and recover after restart.
- Provide secure tenant-scoped playback/download for every declared artifact.
- Make failures and nested results understandable in the UI.

**Non-Goals:**

- Arbitrary tenant code, images, commands, custom environment packages, reward functions, or policies.
- Adding an unverified Ant/MJX or another simulation environment merely to increase catalog variety.
- Making the private artifact bucket public or exposing durable presigned URLs.
- Replacing SQLite or the single-replica SaaS architecture in this change.

## Decisions

### Three profiles share the verified Go1 MJX job specification

Quick, Standard, and Quality are complete workload profiles over the same verified Go1 MJX/H100 runtime. A profile owns timesteps, timeout, checkpoint cadence, evaluation episodes, and progression-render scope. Quality retains 100M timesteps; Quick and Standard values are finalized from bounded H100 acceptance results because JAX compilation and finalization impose fixed costs.

This is preferred over exposing three environments now: only Go1 has a pinned MJX config and verified end-to-end artifacts. It is also preferred over SB3 on L40S because allocating a GPU does not make that workflow GPU-accelerated.

### One executable catalog projection drives listing and validation

Production `/training-options` is derived from profiles that resolve to a complete `JOB_SPEC`; `POST /jobs` validates against the same projection before persisting a job. Startup/test invariants reject public entries without a job spec or with a non-MJX/non-H100 production shape.

This is preferred over frontend filtering, which would leave unsupported direct API submissions possible and allow catalog drift.

### End-to-end completion is artifact-gated

Remote Nebius success transitions into a persisted finalization phase. Reconciliation checks the canonical S3 status and required artifact manifest, validates every referenced path under the run prefix, and only then writes `completed`. Deadline expiry or terminal validation errors write `failed` with a phase and sanitized summary.

At startup, the single SaaS replica scans persisted non-terminal jobs and resumes reconciliation using their stored Nebius IDs. Reconciliation must be idempotent and never resubmit a remote job.

This is preferred over treating 409 as an unbounded post-completion settling period, which produces a false completed state and permanent UI skeletons.

### Artifact metadata uses opaque identifiers, not storage keys

The cached manifest maps opaque artifact IDs to validated server-side S3 keys and metadata. Tenant responses contain an application access URL. On access, the backend verifies bearer session, job ownership, and manifest membership, then redirects to a short-lived presigned HTTPS URL by default. The redirect preserves efficient S3 byte-range playback without proxying large videos through the 512 MiB SaaS pod.

An authenticated streaming endpoint with Range forwarding remains the fallback if the object store cannot provide the required content headers. Bare caller-controlled S3 keys are never accepted.

### The result UI is type-aware

The frontend renders scalar metrics as cards, known aggregate objects as labeled summaries, and other nested data in collapsed structured tables/details. MP4 artifacts use one reusable HTML5 player; semantic labels select final, montage, intermediate, and untrained media. Open/download actions target freshly returned tenant-authorized URLs.

### Existing records remain visible

Historical SB3 and failed jobs stay in the dashboard; removal affects new catalog listings and submissions only. Previously completed manifests containing raw media keys are normalized into opaque artifact records on read. Persisted active historical jobs are reconciled or terminally marked stale under the new deadlines.

## Risks / Trade-offs

- [Quick and Standard may not be meaningfully cheaper because of JAX compile/finalization overhead] → Measure bounded H100 runs before publishing duration labels and tune complete profiles, not only timesteps.
- [Three sizes of one environment may feel less varied] → Label them honestly as workload profiles; add Ant or another environment only after the same GPU/artifact gates pass.
- [Presigned redirects expose temporary object-store URLs] → Use short expiry, validate tenant ownership before issuance, keep the bucket private, and never persist URLs.
- [Restart reconciliation can duplicate pollers] → Use the one-replica deployment plus an in-process per-job registry/lock and idempotent state transitions.
- [Artifact-gated completion may turn formerly “completed” runs into failures] → Preserve historical completed records, normalize their manifests lazily, and apply new gating to new/reconciled non-terminal jobs.
- [GPU acceptance incurs cost] → Run local tests first, then one bounded H100 smoke at a time; verify durable artifacts and immediately stop/delete every temporary resource.

## Migration Plan

1. Add backward-compatible job/artifact model fields and SQLite migration behavior; retain existing records.
2. Implement opaque artifact normalization/access and tests before changing the UI links.
3. Add idempotent reconciliation and artifact-gated completion, then reconcile only non-terminal historical records.
4. Introduce the three Go1 profiles behind the executable-catalog invariant; keep the current verified quality profile as default until Quick and Standard acceptance data exists.
5. Update the UI for workload cards, finalization/failure state, structured metrics, and video playback.
6. Run local backend/frontend/deploy tests and image health checks.
7. Build/push an immutable MJX image on the CPU builder if runtime changes are required; stop the builder when inactive.
8. Run bounded Quick then Standard H100 acceptance jobs, verify checkpoint/report/video upload and browser seeking, and delete the H100 after each session.
9. Publish measured guidance, enable all three profiles, deploy through the existing GitOps path, and verify tenant isolation in production.

Rollback restores the previous SaaS image/catalog while leaving additive persisted fields readable. Existing S3 artifacts and historical job records remain untouched.

## Open Questions

- What measured timestep/evaluation/render settings best distinguish Quick and Standard after H100 acceptance?
- Should the default profile be Standard for cost safety or Quality for continuity with the current flagship?
- Does Nebius Object Storage preserve `Content-Type`, `Content-Disposition`, CORS, and byte-range behavior on presigned GETs in the production browser, or is authenticated proxy streaming required?
- Which failure details and remote job ID should be tenant-visible versus restricted to a future operator role?
