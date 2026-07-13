## 1. Catalog and persistence contracts

- [x] 1.1 Add backward-compatible job/artifact model fields for lifecycle phase, artifact readiness, failure phase, and structured artifact metadata; verify existing SQLite records still deserialize.
- [x] 1.2 Define Go1 Quick, Standard, and Quality as complete MJX/H100 workload profiles, initially using conservative bounded values pending measured acceptance.
- [x] 1.3 Derive the public production catalog and submission validation from executable job specs, excluding SB3 and missing-spec combinations.
- [x] 1.4 Add catalog tests proving exactly three GPU profiles are listed, every listed profile builds a valid H100 MJX submission, and removed/unsupported direct requests return 422 before persistence or remote creation.

## 2. Reliable orchestration lifecycle

- [x] 2.1 Refactor remote-success handling so it persists a finalization phase and marks `completed` only after required artifact validation succeeds.
- [x] 2.2 Implement bounded reconciliation for Nebius status, finalization readiness, stale deadlines, and terminal sanitized failure phase/reason.
- [x] 2.3 Resume reconciliation for persisted non-terminal jobs at SaaS startup without resubmitting or creating duplicate pollers.
- [x] 2.4 Add tests for remote success with delayed artifacts, terminal finalization failure, stale `starting` jobs, transient polling/S3 failures, restart recovery, and idempotent completion.

## 3. Secure artifact access

- [x] 3.1 Normalize current and legacy manifests into structured artifact records with opaque IDs, safe labels, media kinds, content types, sizes when available, and validated run-prefix keys.
- [x] 3.2 Add owner-scoped artifact access routes that reject caller-controlled keys and cross-tenant access, returning short-lived presigned GET redirects by default.
- [ ] 3.3 Verify presigned Nebius Object Storage MP4 responses provide correct content type, safe filename behavior, and HTTP byte-range seeking; implement authenticated range proxy fallback only if required.
- [x] 3.4 Add tests for manifest validation, legacy normalization, owner playback/download, fresh URL issuance, arbitrary-key rejection, cross-tenant 404 behavior, and missing objects.

## 4. GPU composer and results UI

- [x] 4.1 Replace environment/backend-oriented production choices with Quick, Standard, and Quality GPU workload cards showing bounded size and provisional/measured duration guidance.
- [x] 4.2 Extend frontend API types and job details to display finalization/artifact readiness, stale state, sanitized failure phase/reason, and authorized remote identity only where permitted.
- [x] 4.3 Render scalar and nested metrics with type-aware cards, summaries, and expandable structured details instead of string coercion.
- [x] 4.4 Build an accessible HTML5 MP4 player with final rollout default selection, human-readable media switching, loading/unavailable/retry states, and open/download actions.
- [ ] 4.5 Add frontend tests for the three-profile composer, hidden unsupported options, finalization and failure states, nested metrics, video selection, artifact retry, and mobile/keyboard accessibility.

## 5. Local and deployment verification

- [x] 5.1 Run backend unit/integration tests, frontend typecheck/tests/build, and deploy production assertions; record exact commands and observed results in `IMPLEMENTATION_LOG.MD`.
- [ ] 5.2 Build and smoke-test the SaaS image locally, verifying historical jobs remain visible and legacy completed manifests normalize without modifying stored S3 objects.
- [x] 5.3 Verify production configuration/readiness requires the immutable MJX image and artifact credentials but no longer requires an SB3 runtime for the GPU-only public catalog.
- [x] 5.4 Update `saas/API_RUNBOOK.md`, architecture notes if boundaries changed, and operator troubleshooting guidance for lifecycle phases, sanitized errors, and artifact access without recording secrets.

## 6. Bounded H100 acceptance and rollout

- [ ] 6.1 Run the cheapest local/image gates, then launch one bounded Go1 Quick H100 acceptance job with an explicit timeout; verify CUDA/JAX discovery, checkpoints, finalization, manifest, and all media before deleting the GPU resource.
- [ ] 6.2 Tune and run one bounded Go1 Standard H100 acceptance job; measure end-to-end time/cost and verify artifact playback/seeking before deleting the GPU resource.
- [ ] 6.3 Re-verify the existing or a bounded Quality path against the immutable image, including 100M-step limits and full artifact set; stop/delete all GPU resources immediately after artifact checks.
- [ ] 6.4 Audit and clean up AI jobs, VMs, disks, public IPs, temporary rules, and failed resources; record non-secret IDs, immutable image digest, measurements, results, and cleanup in `IMPLEMENTATION_LOG.MD`.
- [ ] 6.5 Publish measured Quick/Standard/Quality guidance, deploy the immutable SaaS image through GitOps, and verify production catalog consistency, tenant isolation, failure visibility, MP4 playback/seeking, and download actions.
