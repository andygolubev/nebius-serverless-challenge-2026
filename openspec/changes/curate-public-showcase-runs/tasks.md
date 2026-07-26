## 1. Re-establish the reviewed baseline

- [ ] 1.1 Read `AGENTS.md`, `ARCHITECTURE.md`, this change's proposal/design/specs/runbook, the archived gallery/showcase changes, `saas/API_RUNBOOK.md`, and `IMPLEMENTATION_LOG.MD`; record branch, revision, active change, observed source state, and safe next action without secrets
- [ ] 1.2 Confirm `debug-portal` is checked out, run `openspec list`, preserve unrelated worktree changes, and stop if planned implementation overlaps dirty user files
- [ ] 1.3 Inventory the current SB3/MJX configs, hosted entry points, submitter, finalizer, checkpoint loaders, artifact schemas, public evidence adapter, infrastructure outputs, and tests; map every runbook dependency to an existing or missing implementation
- [ ] 1.4 Re-verify sanitized historical baselines for all seven examples and save only non-tenant metrics/digests needed for regression tests; historical results remain comparison/rollback evidence, not fresh campaign pins
- [ ] 1.5 Add fixtures for real canonical environment identities, nested `success.met`, selected-checkpoint evidence, a completed-but-failed G1, and measured runtime/cost fields; exclude tenant email, bearer tokens, secret selectors, storage credentials, and raw private keys
- [ ] 1.6 Convert every unresolved implementation dependency into an explicit task below; do not launch a paid job while the runbook implementation-complete gate is unavailable

## 2. Define and validate the campaign matrix

- [ ] 2.1 Add `sim2policy/configs/showcase_training_matrix.yaml` with a schema version and the exact seven run cards from `execution-runbook.md`; prohibit extra example IDs and unknown fields
- [ ] 2.2 Encode Reacher base 1M/extension 1.5M, seeds 0/7/42, 100k checkpoints, one-hour timeout, hard -10, preferred -7, and deterministic reward/stability ranking
- [ ] 2.3 Encode HalfCheetah base 3M/extension 5M, seeds 0/7/42, 250k checkpoints, two-hour timeout, hard 1500, preferred 2000, and ranking rule
- [ ] 2.4 Encode Ant base 3M/extension 5M, seeds 0/7/42, 250k checkpoints, three-hour timeout, hard 1000, preferred reward 2500 plus mean length 850, and ranking rule
- [ ] 2.5 Encode Hopper base 5M/extension 8M, seeds 0/7/42, 250k checkpoints, three-hour timeout, hard 1000, preferred reward 1800 plus mean length 500, and ranking rule
- [ ] 2.6 Encode Walker2D base 5M/extension 8M, seeds 0/7/42, 250k checkpoints, three-hour timeout, hard 1800, preferred reward 3500 plus mean length 1000, and ranking rule
- [ ] 2.7 Encode Go1 base 200M/extension 300M, seeds 0/7/42, 10M checkpoints, H100 preset, 100 GiB disk, two-hour timeout, hard 20/20 no-fall with per-episode 0.5 m/s, and preferred min 0.75/mean 0.9 m/s
- [ ] 2.8 Encode G1 seed 0, H100 preset, 100 GiB disk, five-hour timeout, fixed 450M curriculum total, flat gates at 100M/150M/200M, 25M candidate cadence, no extension, hard 20/20 no-fall with per-episode 0.4 m/s, and preferred mean 0.6 m/s
- [ ] 2.9 Encode selection seeds `[101,151,211,271,331]`, final seeds `[0,1,2,3,4]`, two selection episodes and four final episodes per seed; reject overlapping sets and role ambiguity
- [ ] 2.10 Add typed schema/loading/normalization code that rejects runtime overrides, mutable image tags, preemptible capacity, missing digests, nonpositive steps, invalid extension totals, wrong preset/backend combinations, and changes after campaign initialization
- [ ] 2.11 Add snapshot tests for the normalized matrix and digest plus negative tests for every prohibited override and matrix invariant

## 3. Implement checkpoint evaluation and explicit finalization

- [ ] 3.1 Define a common checkpoint inventory containing backend, run lineage, effective step, native path/object ID, SHA-256 digest, phase, environment identity, and load compatibility
- [ ] 3.2 Implement deterministic SB3 selection evaluation on the configured selection seeds, including mean/std reward and episode-length evidence for every retained candidate
- [ ] 3.3 Implement MJX per-episode selection evidence containing horizon, fall/termination reason, measured forward velocity, mean velocity, episode length, reward, seed, and checkpoint digest
- [ ] 3.4 Implement SB3 ranking exactly as the matrix declares, with deterministic tie-breaking and no final-step preference
- [ ] 3.5 Implement locomotion ranking lexicographically by full-horizon no-fall count, minimum velocity, mean episode length, mean velocity, configured reward, then earlier checkpoint
- [ ] 3.6 Reject any selection/final seed overlap and prove final-seed results are unavailable to the selection function
- [ ] 3.7 Change hosted finalization to accept one explicit selected checkpoint digest and evaluate/render that checkpoint while preserving the final-step checkpoint as labeled progression evidence
- [ ] 3.8 Emit initial, representative intermediate, selected, and final-step videos linked to exact checkpoint steps/digests and metrics; retain regressions rather than silently substituting media
- [ ] 3.9 Extend `metrics.json`, resolved config, report, manifest, and policy bundle with matrix digest, phase lineage, selected checkpoint, ranking explanation, seed roles, hard/preferred results, and measured runtime/cost
- [ ] 3.10 Add tests for earlier-best selection, ties, regression, missing candidates, corrupt checkpoints, incompatible resume, explicit finalization, deterministic videos, manifest checksums, and bundle inventory

## 4. Implement the G1 450M curriculum

- [ ] 4.1 Inspect and record the exact pinned Playground G1 flat/rough environment identities, PPO defaults, reward terms, commands, observations, reset/termination rules, checkpoint compatibility, and current no-push overrides; do not guess field names
- [ ] 4.2 Add one server-owned G1 result profile retaining 8,192 environments, privileged critic, 20-step unroll, 32 minibatches, four updates, entropy cost 0.005, 20 evaluation points, 1,000-step horizon, and disabled pushes unless inspected source requires a reviewed compatibility adjustment
- [ ] 4.3 Define the flat gait prerequisite as deterministic full-horizon commanded motion and no-fall stability on the selection set; add tests proving standing, reward-only improvement, and short motion cannot pass
- [ ] 4.4 Implement the dedicated hosted MJX curriculum entry point: train flat from scratch; evaluate at 100M, 150M, and 200M; select the earliest passing gate; stop diagnostic if none passes
- [ ] 4.5 Resume the exact selected flat checkpoint into the reviewed no-push rough environment and allocate `450M - selected_flat_step` effective steps without exceeding 450M total
- [ ] 4.6 Retain rough candidates every 25M, rank them with the locomotion rule, and final-evaluate only the selected candidate on the disjoint final set
- [ ] 4.7 Record both phase configs, image/config/matrix digests, input/output checkpoint digests, effective-step accounting, JIT/train/eval/render/upload timings, and phase outcomes in one immutable provenance chain
- [ ] 4.8 Ensure rough training does not cancel because an intermediate checkpoint looks weak; only numerical failure, provider failure, or timeout may terminate after rough start
- [ ] 4.9 Prohibit automatic second G1 seed, steps above 450M, L40S comparison, reward mutation, threshold relaxation, or final-set reselection
- [ ] 4.10 Add unit/integration tests for flat pass at 100M/150M/200M, flat failure, correct remainder arithmetic, cross-phase resume, earlier-best rough selection, 450M ceiling, final hard/preferred outcomes, and diagnostic finalization

## 5. Implement the resumable campaign CLI

- [ ] 5.1 Implement `init` with campaign-ID validation, normalized matrix digest, atomic non-secret state, append-only journal, campaign lock, ordered examples, and refusal to reuse an ID for a different digest
- [ ] 5.2 Implement states `PLANNED`, `PREFLIGHTED`, `SUBMITTED`, `RUNNING`, `FINALIZING`, `VERIFIED`, `ACCEPTED`, `REJECTED`, `NEEDS_HUMAN`, and `CLEANED` with validated transitions and one active remote job invariant
- [ ] 5.3 Implement stable exit codes 0/10/20/30/40 and a redacted structured envelope with exact `next_command`; ensure raw environment/provider errors cannot leak credentials
- [ ] 5.4 Implement `implementation-gate` that proves matrix, runner, finalizer, curriculum, artifact verifier, cloud auditor, immutable images, smoke tests, local suites, and stopped builder before paid work
- [ ] 5.5 Implement `preflight` for branch/revision, tracked overlap, immutable image digest, GitHub Actions status, infrastructure outputs, credential availability without value disclosure, preset/quota, disk/timeout, non-preemptible flag, and cloud baseline
- [ ] 5.6 Implement `plan` with exact run ID/prefix, backend/module, image/config/matrix digests, steps/cadence/seeds, hardware/timeout, parent lineage, required artifacts/gates, retry allowance, cleanup action, and redacted provider preview
- [ ] 5.7 Implement plan-digest confirmation and reject any submission whose normalized plan differs from the reviewed plan
- [ ] 5.8 Implement `submit` with deterministic non-tenant run IDs, idempotency key, exact immutable tag/digest, existing infrastructure/secret selectors, no secret output, and no direct mutable CLI overrides
- [ ] 5.9 Implement `watch` with 60-second polling, heartbeats, effective-step/last-checkpoint/finalization progress, terminal recognition, safe re-entry, and needs-human after five minutes of missing heartbeat while provider state remains active
- [ ] 5.10 Implement `verify`, `select`, `extend`, `accept`, `cleanup`, `audit-cloud`, `status`, and `handoff` according to the runbook, with every command idempotent
- [ ] 5.11 Implement stale-lock recovery that proves no live local process and changes no remote state; prohibit force-clearing an active campaign lock
- [ ] 5.12 Add state-machine tests for interruption/resume, duplicate command, concurrent invocation, duplicate remote name with matching/mismatching digest, unknown provider state, finalization-only retry, compatible/incompatible resume, and cleanup blocking
- [ ] 5.13 Add redaction tests using sentinel secrets across stdout/stderr/state/journal/plans/audits/handoff and fail the suite if any sentinel appears

## 6. Implement immutable acceptance and public evidence handling

- [ ] 6.1 Define a typed allowlisted curated-evidence model for canonical environment, sanitized resolved config, runtime versions, matrix/image/config/checkpoint/manifest digests, selection/final metrics, progression media, measured runtime/cost, and acceptance timestamp
- [ ] 6.2 Add exact canonical identity mappings for Reacher, HalfCheetah, Ant, Hopper, Walker2D, Go1, G1 flat, and G1 rough; reject fuzzy, friendly-only, unknown, and caller-controlled identity values
- [ ] 6.3 Normalize only recognized `success.met` shapes and reject missing, contradictory, non-boolean, threshold-inconsistent, or ambiguous legacy values
- [ ] 6.4 Verify every required object, checksum, content linkage, policy bundle member, selected checkpoint, progression entry, and public fixture against the exact curated prefix without cross-run fallback
- [ ] 6.5 Make the curator reject tenant-shaped IDs, placeholders, duplicate pins, mutable images, failed hard/preferred targets, missing cleanup proof, unsafe fields, and incomplete measured evidence
- [ ] 6.6 Keep historical accepted runs available only as named baselines/rollback targets; require an explicit reviewed decision before using one instead of a fresh accepted run
- [ ] 6.7 Refactor public serialization to use measured curated evidence rather than catalog defaults for executed config, hardware, duration, cost, versions, checkpoint, success, and progress
- [ ] 6.8 Keep the public resolver structurally separate from tenant lookup and prove headers, tenant IDs/run IDs, object keys, query overrides, and write methods cannot influence evidence resolution or start work
- [ ] 6.9 Add backend/frontend fixtures and tests for all fresh accepted shapes, completed failure, hard-only/preferred-fail, partial publication, stable order, selected-versus-final progress, regressions, anonymous equality, media/downloads, 404 isolation, and no training actions

## 7. Build immutable images and pass increasing-cost gates

- [ ] 7.1 Run local lint, type, unit, integration, frontend, production-build, `git diff --check`, secret scan, large-file scan, and `openspec validate curate-public-showcase-runs --strict`; resolve failures before image work
- [ ] 7.2 Start or reuse the approved `cpu-d3` builder with its cached disk, verify ownership/scope, and record non-secret instance state in `IMPLEMENTATION_LOG.MD`
- [ ] 7.3 Build SB3 and MJX images with BuildKit from the exact reviewed commit, tag with immutable commit SHA, run health/import/config/matrix/CLI tests, and push without replacing any tag used by an active job
- [ ] 7.4 Resolve and record registry digests; prove planned configs/modules are present and no secret or generated training artifact is baked into either image
- [ ] 7.5 Run a short bounded CPU SB3 smoke with explicit timeout through the campaign path; verify one update, checkpoint, explicit finalization, durable upload, artifact read, cleanup, and idempotent re-entry
- [ ] 7.6 Run a short bounded single-H100 MJX smoke with explicit timeout; verify CUDA/JAX device discovery, compile, flat/rough environment construction, one update per path, checkpoint resume, selection evaluation, render, bundle, upload, and cleanup
- [ ] 7.7 Stop the CPU builder after images are durable; stop/delete smoke compute; audit jobs, instances, disks, IPs, and temporary rules; do not proceed until audit passes
- [ ] 7.8 Re-run `implementation-gate` and archive its sanitized output/digests in the gitignored campaign evidence location

## 8. Execute fresh SB3 campaigns sequentially

- [ ] 8.1 Initialize the campaign exactly as `execution-runbook.md` specifies, confirm matrix digest and order, run global preflight, and write the first sanitized handoff
- [ ] 8.2 Execute Reacher seed 0 through plan/submit/watch/verify/cleanup; record exact state/evidence/cleanup and run no other campaign job concurrently
- [ ] 8.3 Execute Reacher seeds 7 and 42 with the identical matrix contract, verifying and cleaning each before the next
- [ ] 8.4 Run Reacher selection; if required by structured `next_command`, extend only the winning seed to 1.5M; final-accept once and emit accepted/rejected/needs-human without improvisation
- [ ] 8.5 Execute HalfCheetah seeds 0, 7, and 42 sequentially at 3M each, with verification/cleanup after each; select, optionally extend only the winner to 5M, and final-accept once
- [ ] 8.6 Execute Ant seeds 0, 7, and 42 sequentially at 3M each; verify reward and episode-length evidence; select, optionally extend only the winner to 5M, and final-accept once
- [ ] 8.7 Execute Hopper seeds 0, 7, and 42 sequentially at 5M each; verify stability evidence; select, optionally extend only the winner to 8M, and final-accept once
- [ ] 8.8 Execute Walker2D seeds 0, 7, and 42 sequentially at 5M each; verify full-horizon evidence; select, optionally extend only the winner to 8M, and final-accept once
- [ ] 8.9 After every terminal attempt, run the full cloud cleanup audit and stop the campaign on unknown resources, missing durable evidence, or incomplete cleanup
- [ ] 8.10 After each example, generate a handoff containing consumed retries/extensions, winning checkpoint, hard/preferred result, measured runtime/cost, cleanup proof, and exact next command

## 9. Execute fresh Go1 H100 campaign

- [ ] 9.1 Run Go1 preflight and prove H100 preset/quota, immutable MJX digest, 100 GiB disk, two-hour timeout, non-preemptible setting, 200M budget, and zero unaccounted accelerator resources
- [ ] 9.2 Execute Go1 seed 0 at 200M with 10M checkpoints; verify per-episode selection evidence, all artifacts, and cleanup before continuing
- [ ] 9.3 Execute Go1 seeds 7 and 42 under the identical contract, verifying and cleaning each independently
- [ ] 9.4 Rank all Go1 checkpoints across seeds without final-set access; if preferred quality is missed, resume only the selected seed/checkpoint to 300M and consume the sole extension
- [ ] 9.5 Final-evaluate the selected Go1 checkpoint exactly once on 20 episodes; require the per-episode 0.5 m/s/no-fall hard floor and 0.75 minimum/0.9 mean preferred target for automatic acceptance
- [ ] 9.6 Verify selected/final progression media, exact checkpoint digest, report/manifest/bundle, measured H100 runtime/cost, public fixture, and cleanup audit; do not launch an L40S or further seed fallback

## 10. Execute the one G1 H100 result campaign

- [ ] 10.1 Run G1 preflight and prove exact curriculum module/config/matrix/image digests, H100 preset/quota, 100 GiB disk, five-hour timeout, non-preemptible setting, 450M ceiling, no extension, and clean accelerator audit
- [ ] 10.2 Plan and submit seed 0 once; record the immutable run ID, expected prefix, plan digest, flat/rough identities, gate schedule, and cleanup action without secrets
- [ ] 10.3 Watch at 60-second intervals through flat training; rely only on structured gates at 100M, 150M, and 200M and never cancel or alter settings from manual log impressions
- [ ] 10.4 If a flat gate passes, verify exact selected flat checkpoint/digest and automatic remaining-budget arithmetic before rough resume; if none passes by 200M, finalize diagnostics, clean up, and stop G1 at needs-human
- [ ] 10.5 Watch rough training through the fixed 450M total, retaining 25M candidates and regressions; do not use final acceptance seeds or cancel after weak intermediate metrics
- [ ] 10.6 Rank rough checkpoints with the declared locomotion rule and final-evaluate only the selected checkpoint on 20 deterministic episodes
- [ ] 10.7 Require 20/20 1,000-step no-fall episodes with every episode >=0.4 m/s and mean >=0.6 m/s for automatic acceptance; do not lower, average away, or reinterpret any failed episode
- [ ] 10.8 Verify both-phase provenance, selected and final checkpoint evidence/media, report, manifest, native checkpoint, bundle, effective-step total, measured H100 runtime/cost, and public fixture
- [ ] 10.9 Clean up and audit every chargeable resource; retain provider history/SaaS row/S3 evidence; launch no second seed, extra steps, L40S comparison, or reward variant
- [ ] 10.10 Generate the final G1 handoff with pass/fail metrics for every episode, selected checkpoint, flat transition step, total steps, measured timing, consumed retry state, cleanup, and exact blocker or pin-readiness

## 11. Promote accepted examples safely

- [ ] 11.1 For each accepted example, run the curator against the exact fresh non-tenant run and produce a deterministic acceptance record with hard/preferred pass, immutable digests, selected checkpoint, public fixture, and cleanup proof
- [ ] 11.2 Prepare a minimal source change replacing exactly that example's placeholder/current pin; reject tenant-shaped IDs, failed runs, marginal hard-only results, duplicates, or pins not present in the campaign acceptance inventory
- [ ] 11.3 Allow partial publication: accepted examples may ship independently while rejected/needs-human examples remain placeholders or retain their prior accepted pin
- [ ] 11.4 Run complete runtime/backend/frontend suites, production builds, `git diff --check`, secret/large-file scans, and strict OpenSpec validation for each promotion batch
- [ ] 11.5 Review the exact pin diff and acceptance records, then commit/push only `debug-portal`; never commit campaign state, generated runs, checkpoints, logs, media, credentials, environment files, OpenTofu state, or plans
- [ ] 11.6 Use authenticated `gh` to inspect relevant Actions runs and failed logs; do not infer build/deploy success from a push alone
- [ ] 11.7 Verify deployment/ArgoCD health, then anonymously test catalog/detail/progress playback/seeking/downloads on desktop and 375px light/dark layouts with no training action or secret/storage leak
- [ ] 11.8 Verify signed-in tenant custom training/history, private artifact isolation, and user jobs remain unchanged by public pins

## 12. Close out and hand off

- [ ] 12.1 Run a final cloud audit covering Serverless AI jobs, H100/L40S/CPU instances, builder, disks, public IPs, temporary security rules, durable prefixes, SaaS rows, and provider-history retention; stop/delete every chargeable VM
- [ ] 12.2 Produce a final campaign table for all seven examples with state, selected run/checkpoint, base/extension steps, hard/preferred metrics, measured duration/cost, retry/extension use, public pin state, and cleanup result
- [ ] 12.3 Record accepted pins, unpublished examples, exact blockers, commands/results, and safe next actions in `IMPLEMENTATION_LOG.MD` without credentials or secret selectors
- [ ] 12.4 Update architecture/operator documentation for the campaign matrix, state machine, explicit checkpoint finalization, G1 curriculum, recovery, cleanup, and public acceptance flow
- [ ] 12.5 Re-run all local gates and `openspec validate curate-public-showcase-runs --strict`; check off tasks only after their evidence exists and archive the change only after implementation and production verification are complete
