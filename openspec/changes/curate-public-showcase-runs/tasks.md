## 1. Baseline and real-evidence fixtures

- [ ] 1.1 Re-read `ARCHITECTURE.md`, this change's proposal/design/specs, the archived public-showcase and trainable-gallery changes, `saas/API_RUNBOOK.md`, and current `IMPLEMENTATION_LOG.MD`; record the observed branch, retained-run baseline, commands, blockers, and safe next action without overwriting unrelated work
- [ ] 1.2 Confirm `debug-portal` is checked out, preserve unrelated worktree changes, run `openspec list`, and verify no implementation commit/push targets `main`
- [ ] 1.3 Read-only audit the six named non-tenant source prefixes and capture sanitized fixtures for status, artifacts manifest, metrics, resolved configuration, runtime versions, checkpoint metadata, and progress media; exclude bucket/key/credential/secret/tenant fields
- [ ] 1.4 Add a regression fixture for the inspected below-threshold 25M G1 shape (`success.met=false`, canonical environment, completed artifacts) without including tenant identity or provider-private data
- [ ] 1.5 Add tests proving current synthetic assumptions fail against real runtime shapes: friendly versus canonical environment IDs, `success.met` object versus boolean, and catalog defaults versus measured run evidence

## 2. Typed curated evidence and promotion tooling

- [ ] 2.1 Define typed internal models for sanitized resolved configuration, runtime versions, normalized evaluation, measured benchmark/runtime, selected checkpoint, progression stages, and immutable curation provenance
- [ ] 2.2 Extend the S3 artifact reader with a showcase-evidence read that validates the existing checksummed manifest/bundle and parses only allowlisted fields from resolved config, runtime versions, metrics, checkpoint metadata, and progression evidence
- [ ] 2.3 Add exact server-owned canonical runtime environment mappings for all seven examples and reject unknown, fuzzy, caller-controlled, or mismatched identities
- [ ] 2.4 Normalize only recognized task-success schemas, including the runtime `success.met` object; reject missing, contradictory, non-boolean, legacy ambiguous, or threshold-inconsistent results
- [ ] 2.5 Add durable evidence caching keyed by hardcoded run ID plus evidence digest, with additive migration and disposable/rebuildable rows that cannot collide with tenant artifact cache keys
- [ ] 2.6 Implement a CLI/operator curator that accepts only server-owned example IDs plus non-tenant run IDs, validates immutable provenance and public-schema compatibility, and emits a deterministic acceptance record with no storage or secret details
- [ ] 2.7 Make the curator reject tenant-shaped IDs, placeholder IDs, mutable image tags, duplicate pins, private robot/setup evidence, failed task gates, unsafe config fields, missing progress, or incomplete cost/provenance
- [ ] 2.8 Add unit/integration tests for accepted SB3/MJX records, every fail-closed branch, deterministic output, cache digest invalidation, cross-boundary isolation, and zero training/storage mutation during audit

## 3. Checkpoint progression, selection, and media

- [ ] 3.1 Add a structured progression schema containing exact step, checkpoint digest, selection seeds, per-episode/aggregate task metrics, criterion/result, evaluation runtime, rank, regression state, and rollout ID
- [ ] 3.2 Add deterministic selection-seed configuration disjoint from the existing final acceptance seeds and reject any curation record whose selection/final sets overlap
- [ ] 3.3 Implement SB3 checkpoint ranking by configured deterministic mean-reward criterion and locomotion ranking by full-horizon no-fall count, minimum forward velocity, mean episode length, then mean velocity
- [ ] 3.4 Evaluate only a bounded shortlist on the final seed set, record the selected checkpoint explicitly, and never auto-select the final step or highest scalar reward
- [ ] 3.5 Extend resolved config, `metrics.json`, and Markdown reporting with structured progress and selected-checkpoint provenance while preserving backward compatibility for historical non-curated runs
- [ ] 3.6 Render deterministic initial, representative intermediate, selected, and final-step rollouts; label exact steps/digests/selection and retain visibly regressed final media when an earlier checkpoint wins
- [ ] 3.7 Make `video_final` use the selected passing checkpoint for curated runs, link every progress media item to its metrics record, and reject unlinked/mislabelled media from curation
- [ ] 3.8 Add runtime tests for ranking ties, regression, missing quarter checkpoint, earlier-best selection, disjoint seeds, progression JSON/report schema, deterministic renders, montage labels, and backwards-compatible normal finalization

## 4. Showcase backend and frontend

- [ ] 4.1 Refactor `ShowcaseService` to consume the typed curated-evidence record instead of deriving executed config, runtime, cost, hardware, checkpoint, or evaluation outcome from current catalog defaults
- [ ] 4.2 Strengthen the publication gate so only recognized `success=true` evidence with matching canonical identity, selected checkpoint, progress, provenance, and required artifacts publishes; completed below-threshold pins remain 404
- [ ] 4.3 Return sanitized measured executed config, runtime/cost/rate date, runtime versions, selected checkpoint, and structured progress stages from catalog/detail without tenant, storage, secret-selector, or unallowlisted fields
- [ ] 4.4 Keep the public resolver structurally separate from tenant lookups and prove that bearer headers, tenant IDs/run IDs, object keys, query overrides, and write methods cannot influence evidence resolution or launch/mutate work
- [ ] 4.5 Update `Showcase`/`ResultPanels` to display measured evidence and exact initial/intermediate/selected progress with honest regression labels and no train/re-run control
- [ ] 4.6 Add backend fixtures/tests for all six real source shapes plus failed G1, partial publication, stable order, catalog/default drift, cache rebuild, anonymous equality, artifact playback/download, 404 isolation, and sanitized upstream failures
- [ ] 4.7 Add frontend tests for six-card partial publication, selected-versus-final progress, nested metrics, regression labels, missing optional stages, mobile layout, keyboard/video controls, dark/light themes, and absence of training actions

## 5. Audit and publish the six passing examples

- [ ] 5.1 Run local lint/type/test/build gates before any cloud access and validate the curator against sanitized fixtures
- [ ] 5.2 Through read-only artifact access, run the curator on Reacher `gallery-reacher-3aa59b1-20260714a` and verify threshold, immutable provenance, required objects/bundle, measured evidence, progress, and public payload
- [ ] 5.3 Curate HalfCheetah `gallery-halfcheetah-3aa59b1-20260714a` and Ant `gallery-ant-3aa59b1-20260714a` under the same gates
- [ ] 5.4 Curate Hopper `gallery-hopper2m-3aa59b1-20260714a` and Walker2D `gallery-walker2d2m-3aa59b1-20260714a` under the same gates, retaining their rejected shorter-run evidence as diagnostics only
- [ ] 5.5 Curate Go1 `gallery-go1-quality-433f3f9-20260714a`, verify the corrected robot-frame 20/20 1,000-step no-fall result and 0.5 m/s floor, and reject Quick plus the inspected later failed 100M tenant row
- [ ] 5.6 If a passing source lacks required structured progress, run only bounded evaluation/finalization into a new deterministic non-tenant curated prefix, validate it, and leave the historical source untouched; do not repeat training
- [ ] 5.7 Replace exactly the six accepted placeholders in `SHOWCASE_RUNS`, leave G1 pending, add exact acceptance records/tests, and verify no tenant-shaped or failed run ID is present in source
- [ ] 5.8 Run backend/frontend/runtime suites, `git diff --check`, secret/large-artifact scans, and `openspec validate curate-public-showcase-runs --strict` before deployment
- [ ] 5.9 Commit and push only `debug-portal`, use `gh` to verify SaaS/runtime workflows and failed logs, then confirm ArgoCD/deployment health without placing credentials or generated artifacts in Git
- [ ] 5.10 In an anonymous production browser verify six cards in stable order, measured details, progress playback/seeking, downloads, desktop/375px light/dark layout, no console/storage leak, and no training action; verify signed-in custom training/history is unchanged

## 6. Freeze the bounded G1 experiment contract

- [ ] 6.1 Inspect the exact pinned Playground v0.2.0 G1 flat/rough configuration, reward terms, command distribution, reset/termination, observation keys, and resume compatibility inside the immutable MJX image; record evidence rather than guessed overrides
- [ ] 6.2 Define and test the exact selection seeds, final seeds, retained-checkpoint screen size, top-three cap, flat 100M prerequisite, rough maximum 200M, two-regression stop rule, image/config revisions, artifact contract, timeouts, and safe resume digest chain
- [ ] 6.3 Propose one narrowly allowlisted server-owned stability/curriculum candidate at a time, add config/parser/command/container-matrix tests, and reject arbitrary nested reward/environment overrides or tenant-facing parameters
- [ ] 6.4 Add curriculum provenance to hosted MJX training/finalization/policy bundle: every phase records canonical environment, immutable config/image, step budget, input/selected checkpoint digest, runtime/cost, and phase result while final success remains rough-terrain-only
- [ ] 6.5 Run local quality, real MJX container import/environment/initial-policy/resume/evaluation/render/bundle gates, publish an immutable commit-SHA image only after all pass, and stop the CPU builder immediately after image work
- [ ] 6.6 Before paid work, obtain and record operator-approved maximum candidate count, L40S hours, optional H100 hours, dollar ceiling, wall-time deadline, exact immutable image/config, run prefixes, and cleanup actions; if approval is absent, stop with G1 unpublished

## 7. Execute the G1 ladder in increasing cost order

- [ ] 7.1 Audit zero unintended active jobs/instances first, then run one bounded L40S evaluation-only sweep across retained checkpoints from both 200M no-push runs using selection seeds; persist exact rank/progress evidence without training
- [ ] 7.2 Run the unchanged full 20-episode/1,000-step/0.4-m/s/no-fall acceptance set on at most the top three retained checkpoints; if any passes, finalize/promote it and skip every training task below
- [ ] 7.3 After durable sweep evidence is verified, stop/delete chargeable compute as allowed by the retention instruction and audit AI jobs, instances, disks, IPs, rules, and builder state before the next gate
- [ ] 7.4 Only if no retained checkpoint passes, train the frozen 100M flat-terrain no-push prerequisite from scratch on L40S, evaluate/select checkpoints by sustained commanded gait, and stop the ladder if the full-horizon prerequisite fails
- [ ] 7.5 Verify flat artifacts/provenance and clean up/audit chargeable resources before deciding whether rough fine-tuning is allowed
- [ ] 7.6 Only after the flat prerequisite passes, resume its selected digest into the frozen no-push rough-terrain phase on L40S for at most 200M, recording checkpoint progress and stopping after the declared regression/budget gate
- [ ] 7.7 Run final acceptance only on the bounded rough shortlist; require 20/20 full 1,000-step episodes, every episode at least 0.4 m/s with no fall, complete measured provenance/progress/media/checkpoint/bundle evidence, and no post-hoc threshold change
- [ ] 7.8 If L40S passes within bounds, select it and launch no H100 duplicate; use H100 only under the preapproved capacity/wall-time rule with an otherwise identical frozen contract and record why it was necessary
- [ ] 7.9 After every terminal candidate, preserve required provider/SaaS/S3 history, stop/delete every chargeable VM or unneeded instance, audit all cloud resources, and pause promotion on any cleanup blocker
- [ ] 7.10 If the approved candidate/hour/dollar/wall-time ceiling expires without a pass, leave G1 pending, record diagnostics and safe next action, and do not submit more work without a new reviewed change

## 8. Pin G1 and final verification

- [ ] 8.1 For a passing G1 only, run the curator against the exact final non-tenant run, validate both curriculum phases and selected checkpoint digest, and prove the public payload contains measured successful rough-terrain evidence
- [ ] 8.2 Replace the G1 placeholder with the accepted run ID in a separate reviewed source change; add negative tests that every failed 25M/200M/default-push/no-push diagnostic remains unpublishable
- [ ] 8.3 Re-run complete runtime/backend/frontend tests, production builds, `git diff --check`, secret/large-file scans, strict OpenSpec validation, and a final cloud resource audit
- [ ] 8.4 Commit/push only `debug-portal`, verify relevant GitHub Actions with `gh`, deploy normally, and confirm anonymous production shows all seven cards in stable order only if all seven independently pass
- [ ] 8.5 Browser-verify G1 progress and final rollout at desktop/375px light/dark, exact measured metrics/config/runtime/cost, playback/seeking/download, no training controls, and unchanged tenant/private artifact isolation
- [ ] 8.6 Update `ARCHITECTURE.md`, SaaS/operator runbooks, acceptance records, and `IMPLEMENTATION_LOG.MD` with commands/results/blockers/cleanup and no credentials; run `openspec validate curate-public-showcase-runs --strict` and check tasks only after their evidence exists
