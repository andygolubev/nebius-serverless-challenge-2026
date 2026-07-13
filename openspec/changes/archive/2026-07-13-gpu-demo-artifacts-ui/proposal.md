## Why

The public SaaS currently advertises jobs that cannot run on the production backend, hides useful failure information, and exposes completed media as non-downloadable relative object keys. The demo needs a small, truthful GPU-accelerated catalog and a reliable path from job submission through finalized, playable artifacts before custom environments and policies are introduced.

## What Changes

- **BREAKING** Replace the public SB3 and unsupported Ant/MJX options with three bounded Go1 MJX/JAX PPO presets—Quick, Standard, and Quality—using the verified H100 runtime at increasing workload sizes.
- Require every production-visible environment/algorithm/preset to resolve to an executable production job specification; reject or hide catalog entries that cannot be submitted.
- Distinguish remote training success from end-to-end completion: a tenant job becomes `completed` only after required finalization outputs and the artifact manifest are available, with bounded recovery for stale or interrupted polling.
- Return structured artifact metadata and provide tenant-authorized access to each artifact without exposing object-storage credentials or unusable bucket keys.
- Render MP4 results in an HTML5 video player with seeking plus explicit open/download actions, and render nested metrics as structured summaries instead of JavaScript string coercions.
- Show sanitized failure details, failure phase, remote job identity where appropriate, and stale/finalization state in the job UI.
- Keep arbitrary custom code, images, commands, environments, and policies out of scope; this change establishes the reliable GPU-demo boundary that later custom-job work will build on.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `saas-job-customization`: Restrict the public production catalog to three executable GPU-accelerated Go1 MJX PPO workload profiles and enforce catalog/job-spec consistency.
- `saas-nebius-orchestration`: Make end-to-end completion depend on finalized artifacts and add restart/stale-job reconciliation with useful sanitized failure state.
- `saas-artifact-access`: Replace raw object keys with structured, tenant-authorized artifact access suitable for browser playback and download.
- `saas-web-ui`: Present the three GPU workload sizes, playable video results, structured metrics, artifact readiness, and actionable sanitized job failures.

## Impact

- Backend catalog, validation, job models, Nebius orchestration/polling, startup recovery, S3 artifact reader, and artifact API routes under `saas/backend/app/`.
- Composer, dashboard, job detail/results rendering, API types, and video presentation under `saas/frontend/src/`.
- Existing tests for catalog contents, job submission, orchestration state mapping/recovery, tenant isolation, artifact access, and UI behavior.
- OpenSpec contracts for SaaS customization, orchestration, artifact access, and web UI; operator documentation and the SaaS API runbook.
- GPU acceptance requires bounded H100 smoke/standard/quality gates and immediate cleanup of every temporary VM/job resource in accordance with repository operations policy.
