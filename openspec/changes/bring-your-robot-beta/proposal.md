## Why

The curated Go1 demo proves the training pipeline, but robotics teams need to determine whether
their own robot model is structurally usable before investing in custom environment code or GPU
acceptance. A deliberately constrained Bring Your Robot beta can provide a credible product flow
without pretending that an arbitrary upload is already safe or executable on the verified Go1 job
specification.

## What Changes

- Add a tenant-scoped **My Robots** workspace for uploading, validating, listing, inspecting, and
  deleting small self-contained MJCF robot files.
- Accept only primitive-geometry, data-only MJCF within strict size and structural limits; reject
  meshes, includes, plugins, scripts, external paths, entities, and other executable or unresolved
  content.
- Add two redistributable repository samples—a simple quadruped and a simple biped—that exercise
  the exact public upload contract and can be downloaded and re-uploaded during acceptance.
- Add server-owned locomotion task templates and a bounded scene-object catalog so a tenant can
  create a validated setup from a robot, task, floor, ramp, hurdle, step, and box without uploading
  environment code or object files.
- Persist immutable robot versions and environment drafts on the existing tenant-scoped SQLite/PVC
  boundary, including validation summaries and content digests.
- Show honest readiness: validated custom setups are marked `validated`, not `trainable`; custom
  GPU submission remains unavailable until a later change adds and accepts a generic MJX
  environment/training adapter.
- Keep custom object-file upload, arbitrary Python rewards/environments, Docker images, meshes,
  real-robot deployment, and the seven-example trainable gallery out of this bounded beta.

## Capabilities

### New Capabilities

- `saas-robot-assets`: Tenant-scoped constrained MJCF upload, validation, immutable metadata, and
  the two canonical sample robot bundles.
- `saas-environment-builder`: Server-owned locomotion task and primitive-object catalogs plus
  validated tenant environment drafts.

### Modified Capabilities

- `saas-web-ui`: Add My Robots and environment-builder flows with validation diagnostics and
  explicit non-trainable readiness state.
- `saas-data-persistence`: Persist tenant-owned robot metadata/content and environment drafts
  across SaaS restarts using the existing SQLite/PVC durability boundary.

## Impact

- New backend validation, persistence, and tenant-scoped API routes under `saas/backend/app/`.
- New React views, API types, navigation, forms, and responsive styles under `saas/frontend/src/`.
- Lightweight sample MJCF/XML and documentation under `saas/samples/robots/`; no generated
  checkpoints, videos, meshes, or cloud credentials are committed.
- Backend/frontend tests for accepted samples, hostile/unsupported XML, size limits, tenant
  isolation, bounded object composition, persistence, deletion, and honest readiness labels.
- No Nebius job, runtime image, object-storage, infrastructure, or cloud resource changes in this
  beta; the existing production-executable Go1 catalog and job submission boundary remain intact.
