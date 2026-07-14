## 1. Catalog and persistence contracts

- [ ] 1.1 Add shared backend models for the exact seven stable gallery IDs, display metadata,
  recommended configuration, measured guidance, success criteria, acceptance revision, and
  production job-spec reference.
- [ ] 1.2 Add an additive nullable `gallery_example_id` field and migration to persisted jobs, API
  serialization, and historical-job fallback without rewriting existing rows.
- [ ] 1.3 Populate the server-owned catalog with Go1 Walker, Ant Explorer, HalfCheetah Sprint,
  Hopper Balance, Walker2D Stride, G1 Rough Terrain, and Reacher Target in the specified order; retain
  Go1 Standard and Quality only as secondary sizes beneath the Go1 card.
- [ ] 1.4 Implement acceptance-revision gating so an incomplete or stale entry is omitted from
  `/training-options` and rejected by `POST /jobs` before local or remote creation.
- [ ] 1.5 Resolve submissions exclusively from `gallery_example_id` and catalog-declared bounded
  optional fields; reject arbitrary images, commands, code, environment variables, algorithms,
  compute choices, unknown fields, and out-of-range values with field-level 422 responses.
- [ ] 1.6 Add backend tests asserting exact cardinality/order/metadata, one recommendation per card,
  stale-entry hiding, unsafe submission rejection, resolved configuration persistence, legacy Go1
  profile compatibility, server-selected backend enforcement, historical null identity, and Bring
  Your Robot isolation.

## 2. Train, evaluate, and render every example

- [ ] 2.1 Add bounded SB3 training configurations for `Hopper-v5`, `Walker2d-v5`, and `Reacher-v5`,
  and review existing Ant and HalfCheetah configurations for the gallery's single recommended demo
  workload.
- [ ] 2.2 Define task-specific evaluation metrics and explicit acceptance thresholds for all seven
  examples so the UI can report a meaningful primary KPI and pass/fail outcome.
- [ ] 2.3 Extend the SB3 evaluation and rendering path to produce canonical metrics, a final rollout,
  checkpoint identity, resolved configuration, runtime versions, and safe artifact metadata for
  every new environment.
- [ ] 2.4 Declare complete server-owned production job specs for all five SB3 examples, including
  immutable image setting, right-sized CPU or L40S shape, command/config, timeout, bounded fields,
  artifact prefix, and required outputs; prohibit H100 for these specs.
- [ ] 2.5 Keep Go1 on the accepted MJX/H100 path, mark Quick as the gallery recommendation, and
  confirm Quick, Standard, and Quality still resolve to complete immutable job specs.
- [ ] 2.6 Add a bounded `G1JoystickRoughTerrain` MJX configuration, task-specific evaluation and
  rendering contract, artifact requirements, and production job-spec candidates that reuse the
  immutable MJX runtime without changing the Go1 task.
- [ ] 2.7 Add configuration, command-construction, environment import, short train, evaluation,
  headless-render, artifact-contract, and unsafe-run-ID tests for all seven entries.

## 3. Deterministic policy bundle

- [ ] 3.1 Implement a bounded streaming bundle packager that writes canonical `README.md`,
  `manifest.json`, `resolved-config.json`, `evaluation/metrics.json`, `runtime/versions.json`, and
  the backend-native final checkpoint beneath `checkpoint/`.
- [ ] 3.2 Normalize archive member paths, order, timestamps, permissions, and JSON serialization;
  reject traversal, absolute/duplicate names, excessive members/sizes, unsupported types, and
  missing required inputs before publication.
- [ ] 3.3 Include schema/run/example identity, compatibility loader, immutable runtime identity,
  member sizes/types/SHA-256 digests, evaluation command, and clear simulator-only/physical-robot
  safety guidance in the manifest and README.
- [ ] 3.4 Publish `policy-bundle.zip` and its outer digest through both SB3 and MJX finalizers, and
  gate completion of new gallery jobs on readable, fully validated bundle contents while leaving
  historical non-gallery results compatible.
- [ ] 3.5 Normalize the bundle as an opaque `application/zip` artifact and expose it only through
  the existing owned-job stream or short-lived redirect route with a safe attachment filename.
- [ ] 3.6 Add tests for byte-identical regeneration, every member digest, hostile archive inputs,
  missing/corrupt checkpoints, bounded size/count, no secret/log/video inclusion, finalization
  timeout/failure, historical jobs without bundles, range/redirect behavior, and cross-tenant 404.

## 4. Gallery and avatar UI

- [ ] 4.1 Create seven lightweight original repository-owned SVG avatars with consistent geometry,
  same-origin loading, accessible labels, and no third-party asset request.
- [ ] 4.2 Replace the default New Job form with a responsive seven-card gallery driven only by
  `/training-options`, showing task story, expected outcome, backend/hardware, measured time/cost,
  and one clearly marked recommended configuration per card; show backend as a badge and provide
  no global SB3/MJX or hardware selector.
- [ ] 4.3 Add a concise select-review-start flow with only catalog-declared bounded optional fields,
  field-level validation, clear submitting/error states, and no stale control for hidden examples.
- [ ] 4.4 Show gallery avatar/name and live lifecycle in Jobs rows and details, with a generic
  environment/profile fallback for historical jobs whose example identity is null.
- [ ] 4.5 Add component/API tests for exact seven cards, catalog-only rendering, local avatars,
  recommendation review, successful submission, backend-override 422 errors, absence of a global
  backend selector, hidden entries, historical fallback, and the absence of custom
  robot/environment training actions.
- [ ] 4.6 Verify the gallery and review flow at 375 px, tablet, and desktop widths, light/dark themes,
  keyboard-only navigation, screen reader labels, loading/error/empty states, and no horizontal
  scrolling or broken asset request.
- [ ] 4.7 Replace My Robots' misleading “Training coming after GPU validation” controls with clear
  `Model validated` / `Setup validated` copy, an explanation that no accepted custom training
  adapter exists, and an active **Train a verified example** link that preserves the saved setup.
- [ ] 4.8 Add UI tests proving custom validation creates no job, exposes no hidden/disabled GPU
  validation or custom Start Training action, navigates the active handoff to the seven-card
  gallery, and leaves the saved custom robot/setup unchanged.

## 5. Compact result experience

- [ ] 5.1 Redesign the completed job page with a compact top summary for example identity, outcome,
  primary KPI, runtime, cost, checkpoint, final rollout, and the policy-bundle action instead of
  equal-width raw JSON columns.
- [ ] 5.2 Organize resolved configuration, evaluation details, runtime/device versions, raw nested
  metrics, and individual artifacts into readable labeled sections or collapsed details with safe
  formatting for long numbers, identifiers, arrays, and objects.
- [ ] 5.3 Make **Download policy bundle** the primary completed-gallery takeaway, label it for the
  matching simulator, and keep video/report/JSON/checkpoint actions as secondary files; omit the
  bundle action cleanly for historical results.
- [ ] 5.4 Preserve accessible final-rollout playback, progression selection, fresh authorized URL
  retry, byte-range seeking, and individual artifact download behavior.
- [ ] 5.5 Add result-page tests covering completed/finalizing/failed/legacy jobs, KPI and cost
  summaries, nested metrics, long content, bundle presence/absence, compatibility warning,
  player failures, and tenant-authorized downloads.
- [ ] 5.6 Visually verify result pages at 375 px, tablet, and desktop widths plus light/dark themes;
  confirm the key outcome/actions are compact, no raw object becomes a narrow full-height column,
  and no horizontal scrolling occurs.

## 6. Local and integration gates

- [ ] 6.1 Run the complete backend, frontend, and `sim2policy` test suites plus formatting, type,
  lint, migration, and production-build checks; record commands and observed results in
  `IMPLEMENTATION_LOG.MD` without secrets.
- [ ] 6.2 Exercise all seven entries with local/mock API submission through completed finalization,
  then validate result rendering, bundle contents/digests, legacy-job behavior, and tenant
  isolation using generated test artifacts only.
- [ ] 6.3 Build the SaaS container and restart the local stack with persisted data; verify catalog,
  job identity, results, bundles, and pre-change jobs survive process/container restart.
- [ ] 6.4 Run dependency, secret, generated-artifact, and repository-size checks; confirm no
  credentials, checkpoints, run outputs, logs, runtime images, or acceptance media are tracked.
- [ ] 6.5 Update operator and user documentation to explain each example, the browser-visible
  training result, when to download the policy bundle, its exact contents/loader compatibility,
  why it is not a direct physical-robot deployment artifact, and why custom model/setup validation
  is not custom training or a user-triggerable GPU-validation stage.

## 7. Immutable runtime and cloud acceptance

- [ ] 7.1 Start or reuse the approved `cpu-d3` builder, build the SB3 and MJX images with BuildKit,
  run image import/health/render checks, tag and push immutable commit-SHA revisions, record
  non-secret digests/results, and stop the builder immediately after image work.
- [ ] 7.2 In increasing cost order, run bounded acceptance for each of the five SB3 examples on CPU
  or the cheapest validated L40S path with explicit timeouts; verify convergence threshold,
  evaluation, final video, checkpoint, policy bundle, manifest, S3 durability, runtime, and cost.
- [ ] 7.3 Run one bounded Go1 Quick acceptance on the single-H100 shape only after local/image gates;
  verify CUDA/JAX discovery, training threshold, finalization, video, checkpoint, policy bundle,
  durable upload, runtime, and cost, then stop/delete the H100 immediately.
- [ ] 7.4 Run the exact bounded G1 Rough Terrain profile on the smallest L40S candidate and the
  single-H100 candidate with identical image/config/seed gates; compare memory, convergence,
  end-to-end wall time, utilization, artifact completion, and cost-to-result, then select the
  cheapest passing shape and claim H100-required only if L40S fails a declared gate.
- [ ] 7.5 Bind observed duration/cost and passing evidence to each exact config/image/compute
  revision, enable only current accepted entries, and fail release readiness unless all seven cards
  pass the complete train-to-artifact path.
- [ ] 7.6 After every cloud run, delete temporary Serverless AI validation resources and unused
  instances, stop the reusable CPU builder, and audit instances, disks, public IPs, temporary
  security rules, and failed jobs; record cleanup in `IMPLEMENTATION_LOG.MD`.

## 8. Production UI and artifact validation

- [ ] 8.1 Deploy the accepted immutable revisions through the repository's normal CI/GitOps path,
  use `gh` to verify the relevant Actions runs and failed logs, and confirm production health before
  interactive validation.
- [ ] 8.2 In the signed-in production browser, open New Job and click each of the seven gallery cards;
  verify avatar, copy, measured guidance, recommended configuration, backend/hardware, review
  state, absence of a global backend/hardware selector, and Start training behavior at desktop and
  375 px widths.
- [ ] 8.3 Submit one bounded accepted job from each gallery card through the UI, observe each row
  progress through training and finalization, and click the job from the Jobs UI into its result
  page rather than validating only through direct API URLs.
- [ ] 8.4 On every accepted result page, verify compact KPIs, evaluation outcome, runtime/cost,
  rollout playback/seeking, checkpoint identity, resolved config, versions, and nested details;
  download and inspect the policy bundle and one secondary artifact through the visible UI.
- [ ] 8.5 Verify failed/finalizing states, expired-artifact retry, safe filenames, cross-tenant 404,
  historical result fallback, mobile layout, keyboard navigation, light/dark rendering, and that no
  page exposes a Deploy to Robot claim or trains a Bring Your Robot draft.
- [ ] 8.6 In the signed-in production browser, save and reopen a custom setup, confirm the page
  explains validation-only readiness without the misleading GPU-validation control, click **Train
  a verified example**, and verify the gallery opens while the custom setup remains saved.
- [ ] 8.7 Preserve the seven accepted SaaS job rows and their durable artifacts for user review; do
  not delete them during validation. Delete only temporary cloud execution resources after artifact
  durability is confirmed, capture non-secret evidence, and record the final safe state and URLs in
  `IMPLEMENTATION_LOG.MD`.

## 9. Final verification and handoff

- [ ] 9.1 Re-run `openspec validate add-trainable-examples-gallery --strict`, all changed-area
  regression suites, production smoke checks, and the final cloud-resource audit after the last
  fix; record exact results and remaining limitations in `IMPLEMENTATION_LOG.MD`.
- [ ] 9.2 Review every checklist item against the proposal, design, and delta specs; check off only
  tasks with recorded evidence and leave explicit blockers plus the next safe action for any item
  that is not verified.
