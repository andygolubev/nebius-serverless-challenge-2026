## 1. Re-establish the reviewed baseline

- [x] 1.1 Read `AGENTS.md`, `ARCHITECTURE.md`, this change's proposal/design/specs/runbook, the archived gallery/showcase changes, `saas/API_RUNBOOK.md`, and `IMPLEMENTATION_LOG.MD`; record branch, revision, active change, observed source state, and safe next action without secrets
- [x] 1.2 Confirm `debug-portal` is checked out, run `openspec list`, preserve unrelated worktree changes, and stop if planned implementation overlaps dirty user files
- [x] 1.3 Inventory the current SB3/MJX configs, hosted entry points, submitter, finalizer, checkpoint loaders, artifact schemas, public evidence adapter, infrastructure outputs, and tests; map every runbook dependency to an existing or missing implementation
- [x] 1.4 Re-verify sanitized historical baselines for all seven examples using a Nebius CPU verifier job/VM and save only non-tenant metrics/digests needed for regression tests; do not download/process run artifacts on the shared host, and keep historical results as comparison/rollback evidence rather than fresh campaign pins
- [x] 1.5 Add fixtures for real canonical environment identities, nested `success.met`, selected-checkpoint evidence, a completed-but-failed G1, and measured runtime/cost fields; exclude tenant email, bearer tokens, secret selectors, storage credentials, and raw private keys
- [x] 1.6 Convert every unresolved implementation dependency into an explicit task below; do not launch a paid job while the runbook implementation-complete gate is unavailable
- [x] 1.7 Add an execution-location policy and wrapper that allow the shared host only source/planning edits, static Git/OpenSpec inspection, and Nebius/GitHub control-plane or SSH invocation; make every project test/build/import/smoke/campaign/verification/evaluation/render/training/finalization command fail before start unless Nebius instance/job metadata matches an approved resource
- [x] 1.8 Define the sanitized Nebius location-attestation schema with instance/job ID, region, immutable revision/image, command class, and timestamps; add it to every preparation and workload evidence record without credentials

## 2. Define and validate the campaign matrix

- [x] 2.1 Add `sim2policy/configs/showcase_training_matrix.yaml` with a schema version and the exact seven run cards from `execution-runbook.md`; prohibit extra example IDs and unknown fields
- [x] 2.2 Encode Reacher base 1M/extension 1.5M, seeds 0/7/42, 100k checkpoints, one-hour timeout, hard -10, preferred -7, and deterministic reward/stability ranking
- [x] 2.3 Encode HalfCheetah base 3M/extension 5M, seeds 0/7/42, 250k checkpoints, two-hour timeout, hard 1500, preferred 2000, and ranking rule
- [x] 2.4 Encode Ant base 3M/extension 5M, seeds 0/7/42, 250k checkpoints, three-hour timeout, hard 1000, preferred reward 2500 plus mean length 850, and ranking rule
- [x] 2.5 Encode Hopper base 5M/extension 8M, seeds 0/7/42, 250k checkpoints, three-hour timeout, hard 1000, preferred reward 1800 plus mean length 500, and ranking rule
- [x] 2.6 Encode Walker2D base 5M/extension 8M, seeds 0/7/42, 250k checkpoints, three-hour timeout, hard 1800, preferred reward 3500 plus mean length 1000, and ranking rule
- [x] 2.7 Encode Go1 base 200M/extension 300M, seeds 0/7/42, 10M checkpoints, H100 preset, 100 GiB disk, two-hour timeout, hard 20/20 no-fall with per-episode 0.5 m/s, and preferred min 0.75/mean 0.9 m/s
- [x] 2.8 Encode G1 seed 0, H100 preset, 100 GiB disk, five-hour timeout, fixed 450M curriculum total, flat gates at 100M/150M/200M, 25M candidate cadence, no extension, hard 20/20 no-fall with per-episode 0.4 m/s, and preferred mean 0.6 m/s
- [x] 2.9 Encode selection seeds `[101,151,211,271,331]`, final seeds `[0,1,2,3,4]`, two selection episodes and four final episodes per seed; reject overlapping sets and role ambiguity
- [x] 2.10 Add typed schema/loading/normalization code that rejects runtime overrides, mutable image tags, preemptible capacity, missing digests, nonpositive steps, invalid extension totals, wrong preset/backend combinations, and changes after campaign initialization
- [x] 2.11 On the Nebius CPU orchestration VM, run snapshot tests for the normalized matrix and digest plus negative tests for every prohibited override and matrix invariant; retain the location attestation with the result

## 3. Implement checkpoint evaluation and explicit finalization

- [x] 3.1 Define a common checkpoint inventory containing backend, run lineage, effective step, native path/object ID, SHA-256 digest, phase, environment identity, and load compatibility
- [x] 3.2 Implement deterministic SB3 selection evaluation on the configured selection seeds, including mean/std reward and episode-length evidence for every retained candidate
- [x] 3.3 Implement MJX per-episode selection evidence containing horizon, fall/termination reason, measured forward velocity, mean velocity, episode length, reward, seed, and checkpoint digest
- [x] 3.4 Implement SB3 ranking exactly as the matrix declares, with deterministic tie-breaking and no final-step preference
- [x] 3.5 Implement locomotion ranking lexicographically by full-horizon no-fall count, minimum velocity, mean episode length, mean velocity, configured reward, then earlier checkpoint
- [x] 3.6 Reject any selection/final seed overlap and prove final-seed results are unavailable to the selection function
- [x] 3.7 Change hosted finalization to accept one explicit selected checkpoint digest and evaluate/render that checkpoint while preserving the final-step checkpoint as labeled progression evidence
- [x] 3.8 Emit initial, representative intermediate, selected, and final-step videos linked to exact checkpoint steps/digests and metrics; retain regressions rather than silently substituting media
- [x] 3.9 Extend `metrics.json`, resolved config, report, manifest, and policy bundle with matrix digest, phase lineage, selected checkpoint, ranking explanation, seed roles, hard/preferred results, and measured runtime/cost
- [x] 3.10 On Nebius CPU compute, run tests for earlier-best selection, ties, regression, missing candidates, corrupt checkpoints, incompatible resume, explicit finalization, deterministic videos, manifest checksums, and bundle inventory; execute any simulator/render test only inside the immutable Nebius image

## 4. Implement the G1 450M curriculum

- [x] 4.1 Inspect and record the exact pinned Playground G1 flat/rough environment identities, PPO defaults, reward terms, commands, observations, reset/termination rules, checkpoint compatibility, and current no-push overrides; do not guess field names
- [x] 4.2 Add one server-owned G1 result profile retaining 8,192 environments, privileged critic, 20-step unroll, 32 minibatches, four updates, entropy cost 0.005, 20 evaluation points, 1,000-step horizon, and disabled pushes unless inspected source requires a reviewed compatibility adjustment
- [x] 4.3 Define the flat gait prerequisite as deterministic full-horizon commanded motion and no-fall stability on the selection set; add tests proving standing, reward-only improvement, and short motion cannot pass
- [x] 4.4 Implement the dedicated hosted MJX curriculum entry point: train flat from scratch; evaluate at 100M, 150M, and 200M; select the earliest passing gate; stop diagnostic if none passes
- [x] 4.5 Resume the exact selected flat checkpoint into the reviewed no-push rough environment and allocate `450M - selected_flat_step` effective steps without exceeding 450M total
- [x] 4.6 Retain rough candidates every 25M, rank them with the locomotion rule, and final-evaluate only the selected candidate on the disjoint final set
- [x] 4.7 Record both phase configs, image/config/matrix digests, input/output checkpoint digests, effective-step accounting, JIT/train/eval/render/upload timings, and phase outcomes in one immutable provenance chain
- [x] 4.8 Ensure rough training does not cancel because an intermediate checkpoint looks weak; only numerical failure, provider failure, or timeout may terminate after rough start
- [x] 4.9 Prohibit automatic second G1 seed, steps above 450M, L40S comparison, reward mutation, threshold relaxation, or final-set reselection
- [x] 4.10 On Nebius CPU/GPU compute as appropriate, run unit/integration tests for flat pass at 100M/150M/200M, flat failure, correct remainder arithmetic, cross-phase resume, earlier-best rough selection, 450M ceiling, final hard/preferred outcomes, and diagnostic finalization; no G1/JAX/MuJoCo import or test may run on the shared host

## 5. Implement the resumable campaign CLI

- [x] 5.1 Implement `init` with campaign-ID validation, normalized matrix digest, atomic non-secret state on the Nebius orchestration VM's managed disk, append-only journal, campaign lock, ordered examples, location attestation, and refusal to reuse an ID for a different digest
- [x] 5.2 Implement states `PLANNED`, `PREFLIGHTED`, `SUBMITTED`, `RUNNING`, `FINALIZING`, `VERIFIED`, `ACCEPTED`, `REJECTED`, `NEEDS_HUMAN`, and `CLEANED` with validated transitions and one active remote job invariant
- [x] 5.3 Implement stable exit codes 0/10/20/30/40 and a redacted structured envelope with exact `next_command`; ensure raw environment/provider errors cannot leak credentials
- [x] 5.4 Implement `implementation-gate` that proves an approved Nebius execution location, matrix, runner, finalizer, curriculum, artifact verifier, cloud auditor, immutable images, Nebius smoke tests, Nebius-executed suites, and stopped/in-use-accounted builder before paid work
- [x] 5.5 Implement `preflight` for branch/revision, tracked overlap, immutable image digest, Nebius quality-gate attestations, informational GitHub Actions/deployment status, infrastructure outputs, credential availability without value disclosure, preset/quota, disk/timeout, non-preemptible flag, and cloud baseline; never accept a GitHub-hosted workload check in place of Nebius evidence
- [x] 5.6 Implement `plan` with exact run ID/prefix, backend/module, image/config/matrix digests, steps/cadence/seeds, hardware/timeout, parent lineage, required artifacts/gates, retry allowance, cleanup action, and redacted provider preview
- [x] 5.7 Implement plan-digest confirmation and reject any submission whose normalized plan differs from the reviewed plan
- [x] 5.8 Implement `submit` with deterministic non-tenant run IDs, idempotency key, exact immutable tag/digest, existing infrastructure/secret selectors, no secret output, and no direct mutable CLI overrides
- [x] 5.9 Implement `watch` with 60-second polling, heartbeats, effective-step/last-checkpoint/finalization progress, terminal recognition, safe re-entry, and needs-human after five minutes of missing heartbeat while provider state remains active
- [x] 5.10 Implement `verify`, `select`, `extend`, `accept`, `cleanup`, `audit-cloud`, `status`, and `handoff` according to the runbook, with every command idempotent and executable only on the approved Nebius orchestration VM
- [x] 5.11 Implement stale-lock recovery that proves no live campaign process on the Nebius orchestration VM and changes no remote state; prohibit force-clearing an active campaign lock
- [x] 5.12 On the Nebius CPU VM, run state-machine tests for interruption/resume, duplicate command, concurrent invocation, duplicate remote name with matching/mismatching digest, unknown provider state, finalization-only retry, compatible/incompatible resume, cleanup blocking, and host-location rejection
- [x] 5.13 On the Nebius CPU VM, run redaction tests using sentinel secrets across stdout/stderr/state/journal/plans/audits/handoff/location attestations and fail the suite if any sentinel appears

## 6. Implement immutable acceptance and public evidence handling

- [x] 6.1 Define a typed allowlisted curated-evidence model for canonical environment, sanitized resolved config, runtime versions, matrix/image/config/checkpoint/manifest digests, selection/final metrics, progression media, measured runtime/cost, and acceptance timestamp
- [x] 6.2 Add exact canonical identity mappings for Reacher, HalfCheetah, Ant, Hopper, Walker2D, Go1, G1 flat, and G1 rough; reject fuzzy, friendly-only, unknown, and caller-controlled identity values
- [x] 6.3 Normalize only recognized `success.met` shapes and reject missing, contradictory, non-boolean, threshold-inconsistent, or ambiguous legacy values
- [x] 6.4 Verify every required object, checksum, content linkage, policy bundle member, selected checkpoint, progression entry, and public fixture against the exact curated prefix without cross-run fallback
- [x] 6.5 Make the curator reject tenant-shaped IDs, placeholders, duplicate pins, mutable images, failed hard/preferred targets, missing cleanup proof, unsafe fields, and incomplete measured evidence
- [x] 6.6 Keep historical accepted runs available only as named baselines/rollback targets; require an explicit reviewed decision before using one instead of a fresh accepted run
- [x] 6.7 Refactor public serialization to use measured curated evidence rather than catalog defaults for executed config, hardware, duration, cost, versions, checkpoint, success, and progress
- [x] 6.8 Keep the public resolver structurally separate from tenant lookup and prove headers, tenant IDs/run IDs, object keys, query overrides, and write methods cannot influence evidence resolution or start work
- [x] 6.9 On Nebius CPU compute, run backend/frontend fixture suites for all fresh accepted shapes, completed failure, hard-only/preferred-fail, partial publication, stable order, selected-versus-final progress, regressions, anonymous equality, media/downloads, 404 isolation, no training actions, and location-attestation enforcement

## 7. Prepare, test, and build exclusively on Nebius Cloud

- [x] 7.1 On the shared host run only static source/plan inspection (`git diff --check`, `git status`, `rg`, and `openspec validate curate-public-showcase-runs --strict`); do not install dependencies or run project Python/Node/Docker/test/build/import/simulation commands there
- [x] 7.2 Start or reuse the approved Nebius `cpu-d3` `8vcpu-32gb` orchestration/builder VM with a 300–500 GiB cached managed SSD, verify ownership/scope/region, attest its instance identity, check out the exact `debug-portal` revision, and record only non-secret instance state in `IMPLEMENTATION_LOG.MD`
- [x] 7.3 On that Nebius VM install dependencies and run lint, type, unit, integration, backend/frontend, production-build, secret-scan, and large-file gates; store sanitized results plus location/revision attestations and resolve failures before image work
- [x] 7.4 On that Nebius VM build SB3 and MJX images with BuildKit from the exact reviewed commit, tag with immutable commit SHA, run health/import/config/matrix/CLI tests, and push without replacing any tag used by an active job
- [x] 7.5 From the Nebius VM resolve and record registry digests; prove planned configs/modules are present and no secret or generated training artifact is baked into either image
- [x] 7.6 Run a short bounded Nebius CPU SB3 smoke with explicit timeout through the campaign path; verify one update, checkpoint, explicit finalization, durable upload, cloud-side artifact read, cleanup, idempotent re-entry, and location attestation
- [x] 7.7 Run a short bounded Nebius single-H100 MJX smoke with explicit timeout; verify CUDA/JAX device discovery, compile, flat/rough environment construction, one update per path, checkpoint resume, selection evaluation, render, bundle, upload, cleanup, and location attestation
- [x] 7.8 Stop/delete smoke compute; stop the CPU orchestration/builder whenever no active preparation/control/verification process needs it; audit jobs, instances, disks, IPs, and temporary rules and do not proceed until audit passes
- [x] 7.9 Restart/attest the Nebius orchestration VM only when needed, re-run `implementation-gate` there, and archive its sanitized output/digests on the VM's gitignored campaign state plus the approved durable evidence location

## 8. Execute fresh SB3 campaigns sequentially

- [x] 8.1 From the attested Nebius orchestration VM, initialize the campaign exactly as `execution-runbook.md` specifies, confirm matrix digest and order, run global preflight, and write the first sanitized handoff; the shared host only invokes/observes the cloud command
- [x] 8.2 Execute Reacher seed 0 through plan/submit/watch/verify/cleanup; record exact state/evidence/cleanup and run no other campaign job concurrently
- [x] 8.3 Execute Reacher seeds 7 and 42 with the identical matrix contract, verifying and cleaning each before the next
- [x] 8.4 Run Reacher selection; if required by structured `next_command`, extend only the winning seed to 1.5M; final-accept once and emit accepted/rejected/needs-human without improvisation
- [x] 8.5 Execute HalfCheetah seeds 0, 7, and 42 sequentially at 3M each, with verification/cleanup after each; select, optionally extend only the winner to 5M, and final-accept once
- [x] 8.6 Execute Ant seeds 0, 7, and 42 sequentially at 3M each; verify reward and episode-length evidence; select, optionally extend only the winner to 5M, and final-accept once
- [x] 8.7 Execute Hopper seeds 0, 7, and 42 sequentially at 5M each; verify stability evidence; select, optionally extend only the winner to 8M, and final-accept once
- [x] 8.8 Execute Walker2D seeds 0, 7, and 42 sequentially at 5M each; verify full-horizon evidence; select, optionally extend only the winner to 8M, and final-accept once
- [x] 8.9 After every terminal attempt, run the full cloud cleanup audit and stop the campaign on unknown resources, missing durable evidence, or incomplete cleanup
- [x] 8.10 After each example, generate a handoff containing consumed retries/extensions, winning checkpoint, hard/preferred result, measured runtime/cost, cleanup proof, and exact next command

## 9. Execute fresh Go1 H100 campaign

- [x] 9.1 Run Go1 preflight and prove H100 preset/quota, immutable MJX digest, 100 GiB disk, two-hour timeout, non-preemptible setting, 200M budget, and zero unaccounted accelerator resources
- [x] 9.2 Execute Go1 seed 0 at 200M with 10M checkpoints; verify per-episode selection evidence, all artifacts, and cleanup before continuing
- [x] 9.3 Execute Go1 seeds 7 and 42 under the identical contract, verifying and cleaning each independently
- [x] 9.4 Rank all Go1 checkpoints across seeds without final-set access; if preferred quality is missed, resume only the selected seed/checkpoint to 300M and consume the sole extension
- [x] 9.5 Final-evaluate the selected Go1 checkpoint exactly once on 20 episodes; require the per-episode 0.5 m/s/no-fall hard floor and 0.75 minimum/0.9 mean preferred target for automatic acceptance
- [x] 9.6 Verify selected/final progression media, exact checkpoint digest, report/manifest/bundle, measured H100 runtime/cost, public fixture, and cleanup audit; do not launch an L40S or further seed fallback

## 10. Execute the original G1 H100 result campaign

This section is retained as historical evidence for the completed rejected campaign. Its remaining
unchecked provenance/budget items are not authorization to rerun the old configuration; the reviewed
recovery work begins at section 13.

- [ ] 10.1 Run G1 preflight and prove exact curriculum module/config/matrix/image digests, H100 preset/quota, 100 GiB disk, five-hour timeout, non-preemptible setting, 450M ceiling, no extension, and clean accelerator audit
- [x] 10.2 Plan and submit seed 0 once; record the immutable run ID, expected prefix, plan digest, flat/rough identities, gate schedule, and cleanup action without secrets
- [x] 10.3 Watch at 60-second intervals through flat training; rely only on structured gates at 100M, 150M, and 200M and never cancel or alter settings from manual log impressions
- [ ] 10.4 If a flat gate passes, verify exact selected flat checkpoint/digest and automatic remaining-budget arithmetic before rough resume; if none passes by 200M, finalize diagnostics, clean up, and stop G1 at needs-human
- [ ] 10.5 Watch rough training through the fixed 450M total, retaining 25M candidates and regressions; do not use final acceptance seeds or cancel after weak intermediate metrics
- [x] 10.6 Rank rough checkpoints with the declared locomotion rule and final-evaluate only the selected checkpoint on 20 deterministic episodes
- [x] 10.7 Require 20/20 1,000-step no-fall episodes with every episode >=0.4 m/s and mean >=0.6 m/s for automatic acceptance; do not lower, average away, or reinterpret any failed episode
- [ ] 10.8 Verify both-phase provenance, selected and final checkpoint evidence/media, report, manifest, native checkpoint, bundle, effective-step total, measured H100 runtime/cost, and public fixture
- [x] 10.9 Clean up and audit every chargeable resource; retain provider history/SaaS row/S3 evidence; launch no second seed, extra steps, L40S comparison, or reward variant
- [x] 10.10 Generate the final G1 handoff with pass/fail metrics for every episode, selected checkpoint, flat transition step, total steps, measured timing, consumed retry state, cleanup, and exact blocker or pin-readiness

## 11. Promote accepted examples safely

- [x] 11.1 For each accepted example, run the curator against the exact fresh non-tenant run and produce a deterministic acceptance record with hard/preferred pass, immutable digests, selected checkpoint, public fixture, and cleanup proof
- [x] 11.2 Prepare a minimal source change replacing exactly that example's placeholder/current pin; reject tenant-shaped IDs, failed runs, marginal hard-only results, duplicates, or pins not present in the campaign acceptance inventory
- [x] 11.3 Allow partial publication: accepted examples may ship independently while rejected/needs-human examples remain placeholders or retain their prior accepted pin
- [ ] 11.4 For each promotion batch run complete runtime/backend/frontend suites, production builds, and executable secret/large-file scans on Nebius CPU compute with location attestations; run only static `git diff --check` and strict OpenSpec validation on the shared host
- [x] 11.5 Review the exact pin diff and acceptance records, then commit/push only `debug-portal`; never commit campaign state, generated runs, checkpoints, logs, media, credentials, environment files, OpenTofu state, or plans
- [x] 11.6 Use authenticated `gh` to inspect relevant Actions runs and failed logs; do not infer build/deploy success from a push alone
- [ ] 11.7 Verify deployment/ArgoCD health, then anonymously test catalog/detail/progress playback/seeking/downloads on desktop and 375px light/dark layouts with no training action or secret/storage leak
- [ ] 11.8 Verify signed-in tenant custom training/history, private artifact isolation, and user jobs remain unchanged by public pins

## 12. Close out and hand off

- [ ] 12.1 Run a final cloud audit covering Serverless AI jobs, H100/L40S/CPU instances, builder, disks, public IPs, temporary security rules, durable prefixes, SaaS rows, and provider-history retention; stop/delete every chargeable VM
- [x] 12.2 Produce a final campaign table for all seven examples with state, selected run/checkpoint, base/extension steps, hard/preferred metrics, measured duration/cost, retry/extension use, public pin state, and cleanup result
- [x] 12.3 Record accepted pins, unpublished examples, exact blockers, commands/results, and safe next actions in `IMPLEMENTATION_LOG.MD` without credentials or secret selectors
- [x] 12.4 Update architecture/operator documentation for the campaign matrix, state machine, explicit checkpoint finalization, G1 curriculum, recovery, cleanup, and public acceptance flow
- [ ] 12.5 Re-run all executable gates on Nebius Cloud and retain their location attestations; on the shared host run only static Git/OpenSpec checks including `openspec validate curate-public-showcase-runs --strict`; check off tasks only after evidence exists and archive only after implementation and production verification are complete

## 13. Implement the reviewed G1 recovery contract

- [x] 13.1 Add exact G1 termination telemetry for `horizon`, `torso_inversion`, `foot_foot_contact`, `foot_shin_contact`, `nan_state`, and `unknown_environment_done`; retain all simultaneous causes, choose the reviewed deterministic primary reason, and keep every non-horizon result a hard-gate failure
- [x] 13.2 Add server-owned `G1ForwardFlatTerrain` and `G1ForwardRoughTerrain` identities over pinned Playground v0.2.0 with identical physics, resets, noise, observations, actions, rewards, and termination rules but an invariant `[1.0, 0.0, 0.0]` command, no zero-command sampling, no effective 500-step command change, and pushes disabled
- [x] 13.3 Extend canonical environment mappings, resolved configuration, policy bundles, public fixtures, and allowlisted curation evidence for the fixed-forward G1 identities without changing tenant G1 joystick training cards
- [x] 13.4 Add an atomic immutable G1 transition record containing source/target environments, exact parent object/path, sidecar step, SHA-256 digest, image/config/matrix digests, measured flat spend, and remaining rough budget; verify the resolved bytes, pinned Brax observation-normalizer/policy/value tuple, and trainer load path before rough PPO updates, and explicitly record fresh seed-0 optimizer/learner-step/rollout-state/PRNG initialization
- [x] 13.5 Make finalization-only G1 recovery consume the recorded transition and exact rough phase; prohibit flat re-evaluation, parent reselection, synthesized lineage, or promotion when the transition record is absent or inconsistent
- [x] 13.6 Extend the matrix schema and normalized plan with the evaluation-only parent sweep, one quantum-aligned 50M-ceiling/90-minute H100 pilot, the structured pilot gate, one conditional fresh 450M/five-hour H100 curriculum, fixed-forward environment identities, one uninterrupted quantum-aligned nominal-150M flat phase and exact derived final gate, 25M checkpoint cadence, seed 0, and no extension or reward override
- [x] 13.7 Implement the fresh flat phase as one uninterrupted request to the largest PPO epoch quantum at or below nominal 150M; assert 149,422,080 effective steps under the reviewed batch contract, gate only that final checkpoint, retain earlier checkpoints as non-transition progression, stop before rough when it fails, and charge all measured flat work before deriving and quantizing the rough remainder
- [x] 13.8 On Nebius CPU/GPU compute as appropriate, test exact termination classification, fixed command invariance through reset and step 1,000, unchanged reward/PPO contract, pinned Brax supported-tuple restore plus explicit learner-state reinitialization, transition mismatch rejection, recovery immutability, derived-flat-gate behavior, PPO-quantum budget arithmetic, pilot gating, final-seed isolation, and host-location rejection
- [x] 13.9 Add the exact `user_reviewed_direct_full_v1` matrix authorization for only campaign `gallery-g1-direct-full-20260803-01`, one job, seed 0, immutable revision/image/matrix binding, fixed-forward identities, 149,422,080 flat plus 300,318,720 rough steps, non-preemptible H100, 100 GiB, five hours, and zero retry/extension/override
- [x] 13.10 Permit G1 full planning without a pilot record only under that exact authorization and reject every mode/campaign/seed/budget/hardware/timeout/digest drift before submission; do not create or infer pilot evidence
- [x] 13.11 On Nebius CPU compute, prove the direct-full plan passes only for the exact reviewed tuple and that missing, generic, mutated, or pilot-shaped authorization cannot bypass the gate

## 14. Record the superseded diagnostic and pilot path

- [x] 14.1 On the attested Nebius builder, run the complete Sim2Policy quality gates, immutable-image content audit, and tracked secret/large-file scans; build and push a commit-tagged MJX image only after they pass, resolve its digest, then stop the builder when no longer needed
- [x] 14.2 Run a one-update H100 smoke through both fixed-forward environments and the transition boundary; prove GPU discovery, command invariance, exact termination telemetry, pinned Brax supported-tuple save/load and declared learner-state reinitialization, durable transition upload, evaluation, rendering, artifact checksums, cleanup, and location attestation
- [x] 14.3 Superseded by the reviewed direct-full decision after the evaluation-only H100 job reached its 90-minute provider timeout without writing a durable eligibility report; retain the failed job and do not claim or infer an eligible parent
- [x] 14.4 Superseded without execution because task 14.3 produced no eligible-parent evidence; submit no pilot and fabricate no pilot transition, gate, or acceptance record
- [x] 14.5 Superseded by `user_reviewed_direct_full_v1`; this is an explicit operator authorization for one exact fresh result campaign, not a claim that the pilot gate passed

## 15. Execute one fresh fixed-forward G1 result campaign

- [x] 15.1 Under the exact reviewed direct-full authorization, run a new campaign preflight that binds campaign `gallery-g1-direct-full-20260803-01`, the recovery matrix/image/config/revision digests, seed 0, non-preemptible H100 preset, 100 GiB disk, five-hour timeout, 450M total ceiling, the derived 149,422,080-step flat gate, the 300,318,720-step rough request, no retry/extension/override, and a clean accelerator audit
- [ ] 15.2 Train `G1ForwardFlatTerrain` uninterrupted from scratch to the asserted 149,422,080 effective-step boundary, evaluate only that final checkpoint on selection seeds, and require 10/10 1,000-step no-termination episodes with every episode at least 0.4 m/s before any rough transition; retain earlier 25M candidates only as progression
- [ ] 15.3 Atomically persist and verify the exact selected flat transition record, then allocate `450M - measured_flat_training_steps` to `G1ForwardRoughTerrain` after rounding down to whole PPO epoch quanta; abort before rough PPO if path, step, digest, environment, or budget differs
- [ ] 15.4 Train the complete declared rough remainder, retain 25M candidates and regressions, and never use final seeds, reward impressions, or rollout appearance to cancel or change the run
- [ ] 15.5 Rank rough checkpoints on the declared selection set by full-horizon no-termination count, minimum velocity, mean length, mean velocity, reward, and earlier step; final-evaluate only the selected checkpoint on four episodes each for final seeds `[0,1,2,3,4]`
- [ ] 15.6 Accept only 20/20 1,000-step no-termination episodes with every episode at least 0.4 m/s and mean at least 0.6 m/s; do not lower thresholds, reinterpret self-contact as success, launch another seed, mutate rewards, continue past 450M, or reselect with final results
- [ ] 15.7 Verify the exact transition and both-phase provenance, selected/final checkpoint evidence and media, termination taxonomy, report, manifest, native checkpoint, policy bundle, measured runtime/cost, public fixture, and effective-step ceiling before curation
- [ ] 15.8 Clean up and audit every chargeable resource, retain provider history/SaaS row/private durable evidence, and generate a final handoff containing the direct-full authorization, exact parent/selected digests, every final episode result, publication decision, and no secret selectors

## 16. Promote and close the recovered G1 result

- [ ] 16.1 Finalize `execution-runbook.md` and update `ARCHITECTURE.md`, operator documentation, and sanitized fixtures for the fixed-forward direct-full flow, exact transition recovery, and termination taxonomy
- [ ] 16.2 If G1 is accepted, run complete runtime/backend/frontend suites, production builds, secret/large-file scans, and strict OpenSpec validation on the required Nebius/static locations; if rejected or needs-human, retain the placeholder and skip source pinning
- [ ] 16.3 For an accepted result only, replace exactly the G1 showcase pin on `debug-portal`, inspect GitHub Actions with `gh`, verify GitOps/ArgoCD rollout, and anonymously test catalog/detail/progression playback/downloads on desktop and 375px light/dark layouts with no tenant/storage leak
- [ ] 16.4 Repeat the final cloud audit, stop/delete every chargeable VM, update `IMPLEMENTATION_LOG.MD` with commands/results/blockers/safe next action, and archive the OpenSpec change only after every required production verification is complete

## 17. Execute the reviewed rough-0.8 G1 replacement

- [x] 17.1 Record the terminal v1 evidence without reinterpreting it: 149,422,080 flat steps, 8/10 selection horizons, no transition, zero rough steps, and an invalid diagnostic touch of final seeds; preserve both prior Serverless AI jobs
- [x] 17.2 Add phase-specific invariant commands—flat `[1.0,0.0,0.0]`, rough `[0.8,0.0,0.0]`—while preserving physics, reset/noise, observations/actions, rewards, termination rules, PPO, pushes-disabled behavior, and unchanged acceptance thresholds
- [x] 17.3 Bind `user_reviewed_rough_08_full_v2` only to campaign `gallery-g1-rough08-full-20260803-01`, seed 0, one non-preemptible H100 job, 100 GiB, five hours, zero retry/extension/override, 199,229,440 flat plus 250,511,360 rough effective steps, and the immutable revision/image/matrix tuple
- [x] 17.4 Repair failure-path final-seed isolation so a failed flat prerequisite atomically persists selection evidence with `final_seeds_touched: []` and returns without generic finalization or any final-seed evaluation
- [x] 17.5 On the approved Nebius builder, run complete quality gates and focused command/budget/isolation tests, build and attest an immutable MJX image, prove both phase commands through reset and step 1,000 on H100, and pass exact campaign implementation/preflight gates
- [x] 17.6 Submit exactly one fresh reviewed job, monitor only structured provider/durable evidence, train the full declared rough remainder after an exact flat pass, and never delete, restart, retry, extend, or override any Serverless AI job
- [ ] 17.7 Verify transition/provenance, candidate ranking, final-seed isolation, 20/20 horizons, every velocity at least 0.4 m/s, mean at least 0.6 m/s, media/camera, artifacts, measured runtime/cost, and cleanup before publication
- [x] 17.8 Publish only an accepted result; otherwise retain the diagnostic privately. Audit all resource scopes, stop chargeable VMs, preserve provider history, and record the final sanitized handoff

## 18. Publish the exact best-available verified G1 recording

- [x] 18.1 Record the operator decision and exact reviewed tuple for `showcase-gallery-g1-20260801-16-g1-s0-rough`; require verified manifest/checksums/bundle/provenance/media while retaining its real 0/20 horizon result and `success: false`
- [x] 18.2 Implement a fail-closed exact-tuple curation exception that publishes the reviewed G1 recording without changing its evaluation result, hard gate, thresholds, or the accepted-only rule for every other run
- [x] 18.3 Replace only the G1 placeholder pin and add backend/frontend coverage proving the run appears as a verified recording with the existing `Below task threshold` badge and no `not verified` label
- [ ] 18.4 Run complete backend/frontend production validation and secret/large-file scans on the approved Nebius builder, retain location evidence, and run static diff/OpenSpec validation on the shared host
- [ ] 18.5 Commit/push only `debug-portal`, inspect GitHub Actions and GitOps rollout, anonymously verify catalog/detail/media/downloads, preserve all Serverless jobs, stop the builder, and record the sanitized final handoff
