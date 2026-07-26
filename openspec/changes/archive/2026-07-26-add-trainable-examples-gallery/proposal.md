## Why

The product currently exposes one trainable robot family and hides the environment builder behind
a validation-only upload flow, so it does not deliver the promised gallery of realistic examples.
Users need a small, trustworthy set of visually distinct tasks that can actually train and produce
a result they can understand, replay, and optionally take away.

## What Changes

- Replace the New Job form's catalog-first presentation with a gallery of exactly seven
  server-owned, production-executable examples: Go1 Walker, Ant Explorer, HalfCheetah Sprint,
  Hopper Balance, Walker2D Stride, G1 Rough Terrain, and Reacher Target.
- Give each example an original local avatar, concise task/environment story, measured runtime and
  cost guidance, backend/hardware badge, expected result, and one recommended bounded training
  configuration. Keep advanced customization intentionally small.
- Use MJX/JAX PPO for Go1 Walker and the complex Unitree G1 rough-terrain flagship, and SB3 PPO for
  the five classic-control examples. The server selects one accepted backend per card; the UI shows
  it as metadata and does not offer a global SB3/MJX selector.
- Add the missing SB3 and G1 MJX configurations, evaluation criteria, rendering support, immutable
  runtime contracts, and right-sized Nebius job specifications required for every published card.
  A card is hidden rather than accepted unless its full train/finalize/artifact path is verified.
- Compare the exact G1 workload on L40S and H100 before selecting its production shape. Label the
  profile H100-required only when recorded evidence shows L40S cannot meet the declared memory,
  convergence, wall-time, or cost-to-result gate and the H100 run passes it.
- Preserve Bring Your Robot as a separate validation-only beta. Uploaded robots and setup drafts do
  not enter this trainable catalog and still cannot be submitted to `/jobs`.
- Replace the misleading disabled “Training coming after GPU validation” state in My Robots with an
  honest explanation that model/setup validation is complete but no accepted custom training
  adapter exists. Preserve the saved setup and provide an active **Train a verified example** link
  to the seven-card gallery instead of implying that another user-triggerable validation step is
  available.
- Make the completed-run outcome explicit: browser-visible KPIs, evaluation, rollout video,
  checkpoint identity, configuration, versions, and cost remain sufficient to understand the run
  without downloading anything.
- Add an optional tenant-authorized **Download policy bundle** action. The bundle contains the final
  checkpoint, resolved configuration, evaluation metrics, runtime/version metadata, manifest with
  checksums, and a README explaining how to reproduce/evaluate it in the matching simulator.
- Keep individual report, JSON, checkpoint, and video downloads available under secondary result
  files. Do not claim the bundle is directly deployable to a physical robot or provide a Deploy to
  Robot action.

## Capabilities

### New Capabilities

- `trainable-examples-gallery`: Exact seven-card gallery contract, metadata, avatars, verified
  executable backing specifications, and gallery-to-job identity.
- `policy-bundle-export`: Deterministic completed-run bundle contents, integrity metadata,
  tenant-authorized delivery, and simulator-only usage guidance.

### Modified Capabilities

- `saas-job-customization`: Expand the public executable catalog beyond the three Go1 sizes while
  retaining allowlisted, bounded server-owned configurations.
- `saas-nebius-orchestration`: Route each verified gallery entry to its accepted backend, immutable
  runtime image, hardware shape, timeout, and artifact prefix.
- `saas-web-ui`: Make New Job gallery-first, carry example identity into Jobs/results, and add the
  primary policy-bundle action without regressing compact results.
- `saas-artifact-access`: Expose the generated policy bundle through the existing tenant-scoped,
  short-lived artifact delivery boundary.

## Impact

- Changes the SaaS catalog/API models, job records, composer, Jobs cards, results UI, artifact
  manifest normalization, and tenant artifact routes under `saas/`.
- Adds bounded SB3 configurations plus G1 MJX evaluation/rendering coverage under `sim2policy/` and
  publishes immutable runtime revisions only after CPU/import/render gates pass.
- Extends existing Nebius orchestration specifications but creates no persistent GPU VM or new
  always-on service. Go1 remains on its accepted H100 shape; G1 uses the cheapest evidence-backed
  L40S or H100 shape that meets its declared profile, while SB3 examples use CPU or the cheapest
  validated L40S path. Every temporary job/instance is deleted after acceptance.
- Adds original lightweight avatar assets, My Robots-to-gallery guidance, and documentation; no
  external image hotlinks, uploaded environment code, user reward code, meshes, or arbitrary
  containers are introduced.
