## 1. Persistence and API contracts

- [x] 1.1 Add the bounded robot, validation-summary, setup, task-template, scene-preset, and
  catalog-object API models, including stable `validated`/`trainable: false` readiness fields and
  field-level validation errors.
- [x] 1.2 Add additive SQLite schema and tenant-scoped stores for immutable robot XML/metadata and
  normalized environment drafts, including digest idempotency, soft deletion, and the 20-robot /
  50-draft tenant quotas.
- [x] 1.3 Add persistence tests proving old databases migrate automatically, robots and drafts
  survive store/process recreation, duplicate content is idempotent, quotas are atomic, and
  cross-tenant reads/deletes return 404.

## 2. MJCF validation and canonical samples

- [x] 2.1 Implement the 1 MiB UTF-8 MJCF validator with pre-parse DTD/entity rejection, prohibited
  element/reference checks, primitive-only geometry, one floating root, unique-name and
  actuator-reference validation, and the documented body/joint/actuator/geom/depth limits.
- [x] 2.2 Add original primitive-only `sample-quadruped.xml` and `sample-biped.xml` files plus a
  README under `saas/samples/robots/`, with no third-party meshes, generated media, or external
  references.
- [x] 2.3 Add authenticated sample list/download and robot upload/list/detail/content/delete routes;
  stream multipart uploads only to the configured bound and return sanitized diagnostics without
  logging or reflecting raw XML.
- [x] 2.4 Add validator and route tests covering both accepted samples, malformed XML, invalid
  UTF-8, oversized input, DTD/entity payloads, includes, meshes/textures/plugins, remote/file paths,
  unknown actuator joints, duplicate names, structural limits, digest stability, deletion, and
  tenant isolation.

## 3. Server-owned task and environment builder

- [x] 3.1 Implement declarative catalogs for the three locomotion tasks, four scene presets, and
  four primitive object types with compatible robot types, user-facing metadata, defaults, and
  numeric bounds.
- [x] 3.2 Implement setup create/list/detail/delete routes that resolve catalog defaults, enforce
  task/robot compatibility, validate arena and six-object limits, persist normalized immutable
  JSON plus digest, and always return the non-trainable readiness reason.
- [x] 3.3 Add builder tests for every task compatibility rule and scene preset, valid custom object
  composition, default resolution, unknown objects, out-of-range and out-of-arena values, excessive
  objects, cross-tenant robot references, forbidden file/URL fields, persistence, and deletion.
- [x] 3.4 Add regression tests proving custom robots/setups remain absent from `/training-options`
  and cannot be submitted through `POST /jobs`, while all existing Go1 workload submissions remain
  unchanged.

## 4. My Robots web experience

- [x] 4.1 Extend the frontend API client and types for multipart robot upload, sample download,
  robot lifecycle operations, builder catalogs, and setup lifecycle operations without weakening
  bearer-session handling.
- [x] 4.2 Add responsive **My Robots** navigation and workspace views for sample downloads, upload,
  sanitized validation feedback, robot cards/details, parsed model statistics, readiness, and
  deletion.
- [x] 4.3 Add the environment builder flow with compatible task cards, scene presets, optional
  bounded catalog-object controls, normalized review/save, and a clear disabled training state;
  provide no object/environment file or URL upload control.
- [x] 4.4 Add keyboard/mobile-accessible styling, loading/empty/error states, and frontend tests for
  valid/invalid uploads, sample discovery, readiness copy, task filtering, object bounds, setup
  saving, deletion, 375px layout, and keyboard operation.

## 5. Compact job results redesign

- [x] 5.1 Redesign the completed-job information hierarchy into a compact header/status area,
  concise lifecycle row, primary result summary, media area, and secondary technical details;
  collapse completed lifecycle/configuration content that does not need permanent full-height
  presentation while preserving failure and finalization visibility.
- [x] 5.2 Add a type-aware result view model that extracts and consistently formats the primary
  KPIs—mean reward, success, runtime, estimated cost, GPU utilization, environment, and final
  checkpoint—using readable labels, bounded precision, duration/currency/percentage formatting,
  and safe wrapping/truncation instead of raw JSON cards.
- [x] 5.3 Replace the equal-width nested-metric grid with compact semantic sections for Evaluation,
  Episodes, Compute, and Run details: show episode summaries in a readable table/list, place
  device/version/run identifiers behind expandable details, and retain an optional structured raw
  diagnostics view without making it the default presentation.
- [x] 5.4 Make the final rollout/player and media selector visually prominent beside the summary on
  wider screens and above details on narrow screens, preserving retry/open/download controls while
  reducing card padding, empty space, and repeated labels.
- [ ] 5.5 Add frontend behavioral and visual-layout coverage for long checkpoints/run IDs, deeply
  nested metrics, many episodes, missing optional metrics, media and no-media results, completed /
  finalizing / failed states, keyboard interaction, dark mode, and 375px/768px/desktop widths;
  render browser screenshots at each width and verify no narrow JSON columns, clipping, or
  horizontal overflow remain.

## 6. Documentation and verification

- [x] 6.1 Update SaaS/API documentation and `ARCHITECTURE.md` with the robot-versus-scene-versus-task
  model, exact MJCF limits, sample workflow, persistence/quota behavior, server-owned object
  choices, readiness semantics, and explicit custom-training/object-upload non-goals.
- [x] 6.2 Run backend formatting/type/tests and frontend typecheck/tests/build; record exact commands
  and observed results in `IMPLEMENTATION_LOG.MD` without credentials or uploaded private models.
- [x] 6.3 Build and smoke-test the production SaaS image with an isolated persistent database:
  upload both samples, create compatible setups, verify hostile input rejection and tenant
  isolation, restart the container, and confirm robots/drafts persist while the Go1 catalog remains
  production-executable only.
- [x] 6.4 Run deploy-manifest and GitOps assertions to confirm the existing SQLite PVC and Recreate
  strategy remain sufficient and that the change introduces no GPU job, runtime image, secret,
  bucket, VM, disk, IP, or other cloud resource requirement.
- [ ] 6.5 After deployment, use an authenticated production browser session and begin acceptance
  from the visible **Jobs** dashboard—not a copied detail URL or API-only check. Click each
  available retained job row, use **Back to jobs** between records, and verify the redesigned detail
  page for at least one completed job plus every failed/finalizing job currently present; record
  only non-secret SaaS job IDs and observed results in `IMPLEMENTATION_LOG.MD`.
- [ ] 6.6 Exercise the completed-job UI through real controls: play and seek the final rollout,
  switch every available media item, expand Evaluation/Episodes/Compute/Run details, test
  open/download actions, refresh and reopen the job from the dashboard, and capture desktop/tablet/
  mobile screenshots. Preserve all SaaS job rows, cached manifests, and S3 run artifacts used for
  acceptance—do not call a job-delete route, remove database records, or delete result objects—so
  the user can validate the same results afterward; this does not relax mandatory cleanup of any
  billable Nebius AI job, VM, disk, IP, or temporary rule created for separate work.
