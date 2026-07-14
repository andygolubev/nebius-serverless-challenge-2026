## 1. Confirm boundaries and freeze versioned contracts

- [x] 1.1 Re-read `ARCHITECTURE.md`, this change's proposal/design/specs, the active Bring Your Robot and trainable-gallery changes, and current `IMPLEMENTATION_LOG.MD`; record dependencies, observed baseline, commands, and safe next step without overwriting unrelated work.
- [x] 1.2 Complete or explicitly reconcile the remaining Bring Your Robot production-acceptance dependency before changing its `trainable: false` response contract, preserving existing robot/setup IDs and soft-delete behavior.
- [x] 1.3 Define versioned JSON schemas and golden fixtures for preparation input manifest, normalized setup, preparation report, preparation API state, resolved custom Job configuration, artifact manifest additions, and policy-bundle manifest.
- [x] 1.4 Freeze the V1 eligibility table to biped/quadruped × Stand Balance/Walk Forward × Flat Arena/Ramp Course with `objects: []`, and add stable ineligibility/failure codes for every excluded beta task, scene, or optional-object case.
- [x] 1.5 Document the training-only MJCF/compiled-model allowlist, including robot-subtree composition, supported primitive collision geometry, free root, hinge joints, motor actuators/control ranges, numeric/dimension bounds, prohibited world features, and sanitized diagnostics.
- [x] 1.6 Define and version the observation/action ordering, normalization and clipping, resets, horizons, rewards, terminations, task success criteria, preparation gate counts/seeds, and profile/fingerprint inputs with golden hashes.
- [x] 1.7 Add configuration contracts for the feature flag, immutable SB3 image digest, typed preparation/training profiles, S3 prefixes, concurrency/start quotas, reconciliation/finalization timeouts, and fail-fast production validation.

## 2. Build the generic custom-robot environment runtime

- [x] 2.1 Add one generic custom-robot module and fixed `prepare`/`train` entrypoint modes to the existing SB3 runtime; verify no API or runtime path invokes Docker build or constructs an image per robot.
- [x] 2.2 Implement the bounded input-manifest loader that reconstructs the server prefix from an opaque identity, checks containment/size/type, downloads exact inputs, and verifies every SHA-256 digest before parsing.
- [x] 2.3 Implement secure reparse plus extraction/composition of the single robot subtree into versioned server-owned Flat Arena and Ramp Course scenes, with deterministic namespace handling and server-owned world settings.
- [x] 2.4 Implement post-compile training eligibility checks for finite mass/inertia/state, dimensions, joints, actuators, explicit control ranges, supported features, and configured resource/complexity bounds.
- [x] 2.5 Implement deterministic observation/action schema derivation, normalization, previous-action/task-target features, finite checks, `[-1, 1]` clipping, and verified actuator mapping; persist schema hashes and ordered labels.
- [x] 2.6 Implement the versioned Stand Balance reset, reward decomposition, fall/non-finite/runaway termination, success metrics, and deterministic evaluation contract.
- [x] 2.7 Implement the versioned Walk Forward reset, forward/lateral/upright reward decomposition, fall/non-finite/runaway termination, success metrics, and deterministic evaluation contract.
- [x] 2.8 Add seeded environment factories for single and vectorized SB3 use, fixed episode horizons, headless rendering, cleanup, and reproducible resolved configuration.
- [x] 2.9 Add focused runtime tests for both canonical robots, both scenes, both tasks, schema stability, action mapping, task metrics, server-world ownership, deterministic resets, and non-finite/runaway termination.

## 3. Implement bounded preparation execution

- [x] 3.1 Add a versioned preparation profile with hard input, CPU, memory, disk, phase, rollout, learning, rendering, artifact, and wall-time bounds and a provisional allowlisted `cpu-d3` shape pending the production benchmark gate.
- [x] 3.2 Implement preparation phases for manifest verification, secure training allowlist, scene composition, pinned MuJoCo compilation, and compiled dynamics/space validation with phase-specific reports.
- [x] 3.3 Run deterministic multi-seed resets plus bounded zero-action and random-action rollouts, recording contacts, state ranges, terminations, performance, and finite/runaway failures without logging XML.
- [x] 3.4 Run the Gymnasium/SB3 environment checker and a mandatory headless render/media probe with bounded output size and clear sanitized failure codes.
- [x] 3.5 Run a very short fixed PPO learn, checkpoint save, clean reload, and deterministic inference/evaluation smoke cycle; treat technical compatibility separately from task-threshold achievement.
- [x] 3.6 Publish a checksummed preparation report containing fingerprint, all gate results, durations, compiled/schema summaries, version provenance, and only bounded tenant-safe diagnostics.
- [x] 3.7 Enforce process/job timeouts and cleanup for compiler, renderer, rollout, and learning failures; verify no stack trace, absolute path, XML, tenant identity, storage key, credential, or raw provider response reaches public state/logs.
- [x] 3.8 Add adversarial fixtures for digest tampering, unsupported actuators/features, invalid control ranges, extreme dynamics, duplicate/tenant world elements, non-finite simulation, compile timeout, render failure, checkpoint mismatch, and missing/invalid report finalization.
- [x] 3.9 Run the preparation entrypoint locally and in the built container for all eight canonical combinations and negative fixtures, capturing bounded timing/memory evidence in `IMPLEMENTATION_LOG.MD`.

## 4. Persist preparation state and expose tenant APIs

- [x] 4.1 Add backward-compatible SQLite migrations for preparation attempts and custom Job provenance fields, including tenant/setup/robot references, state/phase, fingerprint, manifest/report identities, versions, remote identity, failure data, and timestamps.
- [x] 4.2 Implement transactional store operations, uniqueness for one non-terminal setup/fingerprint attempt, atomic concurrency/idempotency reservations, quota release, restart queries, and historical lookup after source soft deletion.
- [x] 4.3 Replace the fixed setup `trainable: false` projection with derived `training_readiness`, eligibility/reason, current preparation summary, and `can_prepare`/`can_start_training` while preserving deterministic legacy defaults when the feature is disabled.
- [x] 4.4 Implement server-side preparation fingerprint calculation and exact input publication from owned active SQLite robot/setup records; reject stale/deleted/cross-tenant resources and unknown request fields before S3 or remote mutation.
- [x] 4.5 Implement `POST /robot-setups/{setup_id}/preparations` with eligibility, identical-fingerprint reuse, atomic reservation, quota checks, mock/real launch, and no caller-selected runtime, resource, or storage fields.
- [x] 4.6 Implement `GET /robot-setups/{setup_id}/preparations/latest` and preparation detail serialization with restart-safe phases, bounded safe diagnostics, report readiness, Retry eligibility, and owner-only 404 semantics.
- [x] 4.7 Implement failed preparation retry as a new attempt for the same fingerprint, and invalidate readiness whenever robot/setup/runtime/adapter/reward/preparation-profile inputs produce a different current fingerprint.
- [x] 4.8 Implement `POST /robot-setups/{setup_id}/training-jobs` with latest-accepted-fingerprint verification, atomic idempotency/active quota guard, immutable run-input snapshot, fixed custom profile, and normal Job creation/response.
- [x] 4.9 Ensure source robot/setup soft deletion blocks new prepare/start actions but preserves preparation history, already-created Job reconciliation, input snapshots, results, and tenant-authorized downloads.
- [x] 4.10 Add API/store tests for the full readiness state machine, eligibility matrix, unknown fields, stale acceptance, retry, double-click/race behavior, quotas, restart reconciliation, migrations, deletion, and cross-tenant non-disclosure.

## 5. Extend typed Nebius orchestration and storage safely

- [x] 5.1 Introduce separate internal typed job specifications and validators for public MJX, custom preparation, and custom SB3 training; keep no generic pass-through submission object.
- [x] 5.2 Refactor the existing GPU-only invariant so public catalog jobs remain immutable MJX/H100 while custom modes require the immutable SB3 digest, fixed entrypoint, allowlisted `cpu-d3` shape, bounded configuration, and accepted server prefix.
- [x] 5.3 Extend the Nebius SDK submission builder for preparation and custom training without accepting tenant images, commands, code, environment variables, hyperparameters, object keys, hardware, or secrets; add serialization-level assertions for emitted requests.
- [x] 5.4 Persist preparation `aijob-*` identities and implement restart-safe polling, provider-state mapping, deadlines, sanitized terminal failures, quota release, and artifact-gated acceptance without duplicate remote creation.
- [x] 5.5 Implement bounded S3 preparation input publication and custom run input snapshotting with canonical content, safe keys, digest/size verification, retries, cleanup of partial objects, and no bearer credentials in data or logs.
- [x] 5.6 Add feature-flag and startup validation so production custom training cannot enable without the immutable SB3 digest, typed CPU profiles, bucket/secret configuration, quotas, and timeouts; keep existing behavior unchanged while disabled.
- [x] 5.7 Extend the mock backend to simulate preparation phases/acceptance/failure and a complete custom training lifecycle with the same input, result, and bundle schemas and no Nebius credentials.
- [x] 5.8 Add orchestration/storage tests for mixed-type rejection, unsafe identities/prefixes, digest mismatch, SDK field derivation, missing configuration, submission/poll/finalization failure, restart recovery, and public MJX regression behavior.

## 6. Train, evaluate, finalize, and export the custom policy

- [x] 6.1 Add the versioned `custom-ppo-quick` resolved profile with fixed SB3 PPO/vectorization/checkpoint/evaluation/artifact values and provisional `cpu-d3` preset/timeout that can be frozen after the benchmark without changing the public request schema.
- [x] 6.2 Implement custom training startup from the immutable run snapshot, re-verify the accepted fingerprint/schema, build vectorized generic environments, and stop before learning on any integrity or compatibility mismatch.
- [x] 6.3 Run fixed PPO training with bounded progress metrics, periodic complete-before-publish checkpoints, deterministic evaluation cadence, and safe failure handling under the normal Job lifecycle.
- [x] 6.4 Implement final deterministic multi-seed evaluation with per-episode reward/length/fall/task metrics, aggregate success under the versioned task rule, runtime/resource metadata, and an honest below-threshold result.
- [x] 6.5 Generate the human summary, reward curve, compact metrics JSON, final rollout MP4, final checkpoint, resolved configuration, runtime versions, exact input snapshots, and validated custom artifact manifest beneath the run prefix.
- [x] 6.6 Build the fixed-layout policy archive containing the final SB3 checkpoint, exact robot XML, normalized setup, feature/action schemas, resolved adapter/reward/profile configuration, runtime/evaluation metadata, internal checksum manifest, and simulator-only README.
- [x] 6.7 Add bounded archive inspection/extraction plus clean-runtime load/inference smoke verification; reject unsafe paths/types, mismatched digests/dimensions, missing contents, external references, and credentials/tenant data.
- [x] 6.8 Gate custom Job `completed` on every required readable, in-prefix, checksummed artifact including MP4 and policy bundle; distinguish training/evaluation success from infrastructure/finalization failure.
- [x] 6.9 Add runtime/finalization tests for successful and below-threshold completion, training timeout/failure, missing or invalid artifacts, final video probe failure, bundle mismatch/path traversal, source deletion, and normal tenant-authorized access.

## 7. Add the preparation-to-training product flow

- [x] 7.1 Extend frontend API types/client calls for derived readiness, preparation status/report, Prepare, Retry, and setup-bound Start training without exposing backend, hyperparameter, hardware, or storage controls.
- [x] 7.2 Update the setup builder/review to clearly identify the V1 trainable task/scene matrix, require no optional objects for training eligibility, and keep wider beta setups saveable with exact ineligibility explanations.
- [x] 7.3 Replace the disabled “Training coming after GPU validation” controls with compact Not prepared/Preparing/Ready/Preparation failed/Ineligible states and an enabled Prepare for training action where eligible.
- [x] 7.4 Add live preparation polling, phase progress, sanitized failure guidance, Retry, stale-fingerprint refresh, disabled duplicate actions, quota feedback, and accessible loading/error states.
- [x] 7.5 Enable Start training only for the latest accepted fingerprint, submit with idempotency protection, and route the returned normal custom Job to the Jobs dashboard/detail.
- [x] 7.6 Add uploaded-robot identity and task/scene/profile context to Job list/detail while keeping gallery and legacy job identities readable and responsive.
- [x] 7.7 Implement the compact custom result presentation: primary rollout player, key task metrics/success, configuration/provenance summary, expandable details, checkpoint/config/bundle actions, and no raw JSON-column layout.
- [x] 7.8 Show the simulator-only/non-physical-deployment disclosure before policy-bundle download and in result context without implying that preparation or simulation success makes hardware deployment safe.
- [x] 7.9 Add frontend tests for every readiness transition, eligibility restriction, Prepare/Retry/Start, double-click/idempotency behavior, polling/failures, completed-below-threshold results, responsive layout, keyboard operation, video, and disclosed download.

## 8. Documentation, CI, image, and deployment safeguards

- [x] 8.1 Update architecture and SaaS/API documentation with the three-stage model (validated → prepared → trained), endpoint/state schemas, V1 limits, fixed CPU profile, result contents, simulator-only meaning, quotas, and explicit no-per-robot-image boundary.
- [x] 8.2 Update the authenticated API runbook with token-safe Prepare/status/Start/result examples that never contain a real token, secret selector, arbitrary S3 key, or tenant-uploaded command.
- [x] 8.3 Add CI gates for backend/frontend/runtime/unit/integration/security tests, schema/golden compatibility, mock end-to-end flow, container import/health, archive validation, and proof that public `/training-options` behavior is unchanged.
- [ ] 8.4 Build the generic SB3 image once on a reusable `cpu-d3` builder with BuildKit, tag/push an immutable Git revision/digest, record the non-secret digest and evidence, then stop the builder immediately while preserving only the useful cache disk.
- [ ] 8.5 Deploy additive migrations/API/UI with `CUSTOM_ROBOT_TRAINING_ENABLED=false`; verify existing login, robots/setups, seven-example gallery, public MJX job submission, dashboard, and result/artifact access before enabling custom starts.
- [ ] 8.6 Configure the immutable SB3 digest, typed `cpu-d3` profiles, MysteryBox-backed storage credentials, quotas, and deadlines without committing secrets; verify fail-fast readiness for incomplete or inconsistent production configuration.
- [x] 8.7 Document rollout/rollback so disabling the flag stops new Prepare/Start requests while reconciliation and authorized access continue for existing preparations/jobs and no historical rows/artifacts are deleted.

## 9. Benchmark and freeze the production CPU profiles

- [x] 9.1 Run local gates first, then bounded Serverless AI preparation smokes on `cpu-d3` candidates beginning with `4vcpu-16gb`; measure compile, rollout, render, short-PPO, memory, disk, startup, and finalization for all eight canonical combinations.
- [x] 9.2 Run bounded `custom-ppo-quick` candidate trainings beginning with `cpu-d3` / `8vcpu-32gb`; measure throughput, wall time, memory, artifact sizes, evaluation behavior, and cost inputs without claiming unmeasured utilization or convergence.
- [x] 9.3 Select the smallest dependable allowlisted preparation/training shapes and freeze disk, timeout, vector count, PPO step budget, cadence, seeds, and observed duration/cost guidance in versioned config, tests, docs, and fingerprints.
- [ ] 9.4 Re-run the canonical preparation and training smoke gates using the frozen profiles and exact immutable image digest; do not enable production if any supported combination violates bounds or fails required artifact/bundle finalization.
- [ ] 9.5 After each benchmark session, confirm no CPU/GPU VM is still running, remove unneeded temporary instances/IPs/rules/failed resources, keep only justified stopped builder cache, and record cleanup and next safe action in `IMPLEMENTATION_LOG.MD`.

## 10. Production browser acceptance and retained evidence

- [ ] 10.1 Enable custom robot training for the acceptance tenant only after frozen-profile, migration, configuration, mock, and regression gates pass; confirm production health and no secret values in UI/API/logs.
- [ ] 10.2 In the deployed in-app browser, download then upload the repository's canonical biped and quadruped MJCF examples through My Robots and verify their immutable digests/validation summaries; do not bypass the UI with direct database edits.
- [ ] 10.3 Through the UI, create the eight supported biped/quadruped × Stand Balance/Walk Forward × Flat Arena/Ramp Course setups with no optional objects and confirm wider/optional-object setups remain explicitly ineligible.
- [ ] 10.4 Click Prepare for training for each supported setup, observe the live phase/status to Ready, exercise at least one safe failed preparation and Retry, and verify browser refresh/SaaS restart reconciliation does not duplicate remote jobs.
- [ ] 10.5 Click Start training from each Ready setup using only the fixed profile, verify one normal Job per action appears in Jobs, and leave every SaaS Job row intact so the user can click and validate it later.
- [ ] 10.6 Open every retained Job in the UI and verify lifecycle, compact result layout, robot/task/scene/profile provenance, honest evaluation success/below-threshold state, key metrics, expandable details, and absence of raw JSON-column rendering.
- [ ] 10.7 Play and seek each final rollout through tenant-authorized media access, download the checkpoint/config/policy bundle, verify the simulator-only disclosure, and load-check each bundle against its recorded runtime/fingerprint.
- [ ] 10.8 Verify cross-tenant preparation/Job/artifact identifiers return 404, arbitrary input/artifact keys cannot be supplied, deleted source setup behavior is safe, and retained historical Jobs/results remain accessible to their owner.
- [ ] 10.9 Verify public seven-example gallery cards and their MJX/SB3 server-selected execution remain unchanged, custom setups never appear in `/training-options`, and public Job/result flows still pass production browser checks.
- [ ] 10.10 Preserve the acceptance tenant's SaaS Job records and S3 result artifacts for user review; clean only temporary build/compute/security resources, audit active/failed Nebius resources, and record URLs/IDs without secrets plus final evidence and cleanup in `IMPLEMENTATION_LOG.MD`.

## 11. Final verification and handoff

- [x] 11.1 Run all backend, frontend, runtime, integration, schema, security, mock, and artifact/bundle tests from a clean environment and record exact passing commands/results.
- [x] 11.2 Run `openspec validate enable-custom-robot-training --strict` and resolve every validation error without marking implementation tasks complete prematurely.
- [x] 11.3 Review the final diff for unrelated edits, generated runs/checkpoints/logs/media/state/plans, credentials, mutable image tags, raw tenant identifiers, or accidental task check-offs and remove only artifacts created by this change.
- [ ] 11.4 Update `IMPLEMENTATION_LOG.MD` with completed task evidence, immutable image/profile versions, non-secret production acceptance references, retained SaaS Jobs/artifacts, cloud cleanup, blockers, and the next safe action for another agent.
