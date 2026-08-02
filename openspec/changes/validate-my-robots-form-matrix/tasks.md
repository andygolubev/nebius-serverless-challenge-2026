## 1. Validation Foundation

- [x] 1.1 Add gitignored validation-run directories and document the stable case ID, result status, catalog fingerprint, timing, resource identity, cleanup, and sanitized diagnostic schemas.
- [x] 1.2 Implement catalog/sample-driven case generators with independent assertions for the current robot types, five compatibility edges, four scenes, four object types, scene capacities, 28 parameter definitions, and eight V1-eligible combinations.
- [x] 1.3 Implement an explicit inventory mapping every My Robots control and lifecycle state to one or more stable scenario IDs, with a completeness failure for unmapped catalog values or controls.
- [x] 1.4 Implement deterministic shard selection, bounded per-case timeouts, result merging, duplicate/missing case detection, and JSON-to-Markdown summary generation.
- [x] 1.5 Add report/artifact secret and private-model-content scans that block publication while preserving only sanitized reproduction evidence.

## 2. Backend Matrix

- [x] 2.1 Parametrize both canonical upload samples through the declared robot-type paths and verify upload diagnostics, validation summaries, idempotency, quotas, download digests, ownership, and soft deletion.
- [x] 2.2 Execute all 20 compatible no-optional-object and 80 single-default-object setup cases against the API and assert normalization, digest/idempotency, scene composition, persistence, and readiness reason.
- [x] 2.3 Cover every incompatible robot/task edge, unknown identifier/field, cross-tenant reference, and stable training-ineligibility reason without partial persistence.
- [x] 2.4 Cover every object parameter at default/minimum/maximum and invalid just-outside/non-finite inputs, asserting exact field diagnostics and no saved setup.
- [x] 2.5 Cover exact and one-over object capacity for every scene preset, including preset objects in the six-object total.
- [ ] 2.6 Cover all eight V1 eligibility combinations plus optional-object, unsupported-task, unsupported-scene, stale fingerprint, preparation failure/retry, quota, and idempotent training-start projections with mock orchestration.
- [x] 2.7 Verify backend shards run concurrently against isolated temporary databases/tenants and merge into the complete expected case set.

## 3. Frontend Component Matrix

- [x] 3.1 Replace ad-hoc My Robots fixtures with catalog-shaped factories and completeness assertions shared by generated component cases.
- [ ] 3.2 Cover sample downloads and all upload form fields, both robot-type selections, missing/invalid input diagnostics, successful cards, statistics/digest, download, delete/cancel, and Build environment actions.
- [ ] 3.3 Cover every compatible task, scene, object type, parameter editor, add/remove operation, review value, client bound, and scene-specific capacity state, including the exact setup payload.
- [ ] 3.4 Cover save errors, normalized saved summaries, reload persistence, setup delete/cancel, and preservation of unrelated tenant rows.
- [x] 3.5 Cover not-prepared, preparing, ready, failed/retry, stale, quota, duplicate-start, ineligible, and verified-example handoff rendering and action rules.
- [ ] 3.6 Verify accessible labels/roles/selected/disabled/alert states, keyboard-only operation, and the 375-pixel layout for the complete upload-to-save workflow.

## 4. Local Full-Stack Browser Suite

- [x] 4.1 Add Playwright as a development-only dependency with a local FastAPI/Vite test harness, temporary SQLite database, mock delivery/orchestration, isolated worker tenants, downloads, and artifact paths.
- [ ] 4.2 Implement quadruped and biped canonical upload-to-model-card paths, including download digest verification and targeted deletion confirmation.
- [ ] 4.3 Implement a catalog-driven pairwise task/scene/object browser set that covers every discrete value, every compatibility edge, parameter bounds, capacity, add/remove, save, and reload persistence.
- [ ] 4.4 Implement preparation, retry, stale, quota, idempotent Start training, failure, and success browser paths against controlled full-stack responses without creating cloud jobs.
- [ ] 4.5 Implement keyboard and 375-pixel browser cases, accessible-state assertions, per-case timeouts, failure screenshots, and sanitized artifacts.
- [x] 4.6 Verify parallel local workers share no mutable tenant, database, idempotency key, download path, or evidence path and clean all created resources.

## 5. CI and Deployed Smoke

- [x] 5.1 Add parallel backend, component, and local-browser shards to the SaaS CI gate with cached Playwright assets, merged coverage reporting, and no Playwright dependency in the production runtime stage.
- [ ] 5.2 Add a manually invoked deployed smoke runner that accepts only an explicit base URL and masked existing test-tenant session, preflights identity/quotas/catalog, and never logs authorization or private XML.
- [ ] 5.3 Implement the default no-cost deployed matrix for both upload paths, task filtering, all scene/object controls, bounds, save/reload/delete, readiness copy, exact created-ID cleanup, and serialized mutation when only one tenant is available.
- [ ] 5.4 Implement separate `remote-preparation` and `remote-training` gates limited to one representative case, with cheap-gate prerequisites, bounded polling, fresh idempotency, sanitized evidence, and mandatory provider resource audit/cleanup.
- [ ] 5.5 Ensure unrequested paid gates report `not-run-cost-gated`, cleanup failures fail the run, and no run can report cloud resources clean while its own work remains active.
- [x] 5.6 Document local, CI, deployed no-cost, and paid-canary commands plus session handling, evidence retention, cleanup, and reproduction guidance without including real credentials or secret selectors.

## 6. Defect Repair and Acceptance

- [x] 6.1 Run the complete backend matrix, record every deterministic product defect or infrastructure blocker in `IMPLEMENTATION_LOG.MD`, add minimal regressions, repair the owning backend boundary, and rerun the affected shards.
- [x] 6.2 Run the complete component and local-browser matrices, add minimal regressions for each deterministic defect, repair the owning frontend/full-stack boundary, and rerun the affected shards.
- [x] 6.3 Run the merged cheap gate, frontend production build, strict OpenSpec validation, `git diff --check`, and tracked-file secret/large-artifact scans; record exact commands and results.
- [x] 6.4 Deploy only through the `debug-portal` GitHub Actions/GitOps path, verify the workflow and rolled production revision, then run the no-cost deployed smoke and targeted cleanup.
- [ ] 6.5 Record an explicit decision for the remote preparation/training canary; if enabled, run at most the designed single case and audit all cloud resources, otherwise record both paths as `not-run-cost-gated` without claiming coverage.
- [ ] 6.6 Summarize final combination/control coverage, repaired defects, remaining infrastructure or paid-gate gaps, cleanup state, and safe next steps in `IMPLEMENTATION_LOG.MD`.
