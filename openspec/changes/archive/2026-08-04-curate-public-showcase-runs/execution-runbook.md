# Result-first showcase campaign execution runbook

## 0. Purpose and authority

This runbook is the execution contract for the seven-example public showcase campaign. It is written
for a lightweight agent that can run commands and report structured output but must not make research,
hyperparameter, cloud, acceptance, or publication decisions.

This document is a plan. The commands and campaign module described below do not necessarily exist
until the implementation sections of `tasks.md` are complete and verified. **Do not launch paid work
by translating this plan into ad-hoc shell commands.** If the named command, schema, test, or state
transition is missing, stop with `NEEDS_HUMAN: IMPLEMENTATION_INCOMPLETE`.

### Absolute execution-location boundary

The shared host is a control-and-edit terminal only. No training job, preparation job, project test,
dependency installation, build, container execution, import/health check, simulator/environment load,
smoke run, campaign state transition, artifact verifier, checkpoint evaluation/selection, renderer,
finalizer, or project Python/Node module may execute on it. All such commands must execute on Nebius
Cloud compute.

Allowed on the shared host:

- edit and inspect source, OpenSpec, and documentation files;
- run `git status`, `git diff`, `git log`, `rg`, and static OpenSpec planning inspection/validation;
- use `gh`, Nebius control-plane commands, or SSH solely to inspect status or cause a command to run
  on Nebius;
- read sanitized reports, digests, and handoffs returned by Nebius.

Forbidden on the shared host:

- `uv run`, project Python modules, `pytest`, linters/type checkers that import project code, Node/npm
  tests/builds, Docker/BuildKit, MuJoCo/JAX/SB3 imports, simulation, rendering, artifact processing,
  campaign CLI execution, and any smoke/training/finalization command;
- downloading native checkpoints, generated media, container layers, or complete private run
  artifacts for local processing.

Before every executable command, the operator must already be inside the approved Nebius CPU
orchestration/builder VM or be submitting a Nebius Serverless AI job. Prompt appearance is not proof.
The command wrapper SHALL obtain a provider instance/job ID and region from instance metadata or the
provider response, compare it with the campaign's approved resource identity, and write a sanitized
location attestation. Missing/ambiguous/local identity returns exit 40 with
`NEEDS_HUMAN: EXECUTION_LOCATION_INVALID` before workload code starts.

The campaign does not authorize:

- editing the matrix during execution;
- changing a seed, step budget, checkpoint interval, timeout, preset, algorithm, or gate;
- launching a fourth base seed, a second extension, any G1 recovery pilot, or any G1 full campaign
  outside the exact `user_reviewed_rough_08_full_v2` authorization;
- using preemptible capacity;
- pinning a hard-floor-only result that misses its preferred target;
- deleting provider job history, SaaS rows, or durable S3 evidence;
- recording credentials, bearer tokens, access keys, secret values, or raw signed URLs;
- touching `main`, or committing/pushing anywhere except `debug-portal`;
- leaving a chargeable VM running after its task completes.

When the matrix and this document conflict, stop. Do not choose one silently.

## 1. Operator invariants

The execution agent SHALL follow these invariants for every invocation:

1. Work from the repository root on `debug-portal`.
2. Read `IMPLEMENTATION_LOG.MD` before acting and append a sanitized handoff after each state change.
3. Execute the campaign CLI only on the approved Nebius orchestration VM for submission, watching,
   verification, selection, extension, cleanup, and promotion preparation. Direct
   `nebius ai job create` and local campaign CLI execution are prohibited during the campaign.
4. Allow at most one active remote campaign job at a time.
5. Use immutable commit-SHA image tags and record their resolved digests.
6. Use non-preemptible capacity.
7. Poll through the CLI; do not manually infer success from a few log lines.
8. Never select a checkpoint by visual appeal or training reward alone.
9. Never rerun final acceptance on multiple checkpoints and choose the lucky result.
10. Finish artifact verification and cleanup before advancing to another seed/example.
11. When a command returns exit code 30 or 40, stop. Do not attempt a workaround.
12. When the task says “record,” store only the CLI's sanitized output and non-secret identifiers.
13. Require a Nebius location attestation for every test, build, smoke, campaign, verification,
    evaluation, render, training, finalization, and cleanup command.

## 2. Planned campaign CLI contract

Implementation SHALL provide the following module and commands. **Every command in this section is
run in the repository checkout on the approved Nebius orchestration VM, never on the shared host.**
The host may establish the SSH session and copy back the sanitized output only.

```bash
uv run python -m sim2policy.showcase_campaign init \
  --campaign-id gallery-result-2026-01 \
  --matrix sim2policy/configs/showcase_training_matrix.yaml

uv run python -m sim2policy.showcase_campaign preflight \
  --campaign-id gallery-result-2026-01

uv run python -m sim2policy.showcase_campaign status \
  --campaign-id gallery-result-2026-01 \
  --format json

uv run python -m sim2policy.showcase_campaign plan \
  --campaign-id gallery-result-2026-01 \
  --example reacher \
  --seed 0

uv run python -m sim2policy.showcase_campaign submit \
  --campaign-id gallery-result-2026-01 \
  --example reacher \
  --seed 0 \
  --confirm-plan-digest PLAN_DIGEST_FROM_PLAN

uv run python -m sim2policy.showcase_campaign watch \
  --campaign-id gallery-result-2026-01 \
  --poll-seconds 60 \
  --until-terminal

uv run python -m sim2policy.showcase_campaign verify \
  --campaign-id gallery-result-2026-01 \
  --example reacher \
  --seed 0

uv run python -m sim2policy.showcase_campaign cleanup \
  --campaign-id gallery-result-2026-01

uv run python -m sim2policy.showcase_campaign select \
  --campaign-id gallery-result-2026-01 \
  --example reacher

uv run python -m sim2policy.showcase_campaign extend \
  --campaign-id gallery-result-2026-01 \
  --example reacher \
  --confirm-plan-digest PLAN_DIGEST_FROM_SELECT

uv run python -m sim2policy.showcase_campaign accept \
  --campaign-id gallery-result-2026-01 \
  --example reacher

uv run python -m sim2policy.showcase_campaign audit-cloud \
  --campaign-id gallery-result-2026-01

uv run python -m sim2policy.showcase_campaign handoff \
  --campaign-id gallery-result-2026-01 \
  --format markdown
```

`PLAN_DIGEST_FROM_PLAN` is a literal digest printed by the preceding cloud-executed command. The agent copies it
unchanged. It is not a placeholder to invent.

The CLI exit-code contract is:

| Exit | Meaning | Agent action |
| ---: | --- | --- |
| 0 | Requested transition completed or was already complete | Read structured `next_action` |
| 10 | Remote job is still active | Run `watch` again after at least 60 seconds |
| 20 | Deterministic rejection recorded; campaign may have a matrix-defined next action | Run `status`; follow only its `next_command` |
| 30 | Human decision or authority required | Stop and deliver `handoff` |
| 40 | Security, provenance, invariant, or cleanup failure | Stop immediately and deliver `handoff` |

The CLI SHALL print a structured envelope with `campaign_id`, `example`, `attempt`, `state`,
`plan_digest`, `remote_id` when known, `evidence_digest` when known, `decision`, `reason_code`,
`cleanup_state`, and `next_command`. Output SHALL be redacted by construction.

## 3. Persistent state contract

`init` creates the following gitignored tree on the managed disk attached to the Nebius
orchestration VM:

```text
.showcase-campaigns/gallery-result-2026-01/
  campaign.json
  state.json
  journal.jsonl
  lock
  plans/
  attempts/
  evidence/
  audits/
  handoff.md
```

Allowed content: campaign and remote job IDs, timestamps, normalized matrix/config/image/checkpoint
digests, effective steps, provider states, sanitized metrics, reason codes, artifact object IDs,
checksums, cleanup results, and next actions.

Forbidden content: access keys, bearer tokens, secret values/selectors copied from live APIs, registry
passwords, raw environment dumps, signed URLs, tenant email, private object keys outside the curated
prefix, and credentials from local config files.

State writes SHALL be atomic. The append-only journal records command name, prior state, resulting
state, exit code, and sanitized evidence digest. The campaign lock SHALL fail rather than wait
indefinitely. A stale lock can be cleared only by a dedicated CLI recovery command that first proves
there is no live campaign process on the Nebius orchestration VM and changes no remote state.

## 4. One-time implementation-complete gate

Before `init`, all items below must be true. If any is false, no paid job is allowed.

- A Nebius CPU orchestration/builder VM is identified, its managed disk is mounted, its exact
  `debug-portal` revision is recorded, and its execution-location attestation passes.
- The campaign matrix exists and passes its schema/unit tests executed on that Nebius VM.
- The hosted SB3 and MJX paths accept an explicit selected checkpoint for finalization.
- The G1 curriculum module passes flat-to-rough resume and provenance tests.
- The campaign CLI passes idempotency, lock, redaction, duplicate-submission, resume, and state-
  transition tests.
- The artifact verifier validates every required object, checksum, policy bundle member, resolved
  configuration, runtime version, selected checkpoint, progression entry, and public API fixture.
- The cloud auditor can enumerate jobs, VMs, disks, public IPs, temporary rules, and builder state.
- The exact SB3 and MJX images are built from the intended `debug-portal` commit, pushed under an
  immutable tag, resolved to digests, and pass image health/import tests.
- A bounded smoke test has proven CUDA/JAX discovery, environment construction, one update,
  checkpoint upload, finalization, and durable artifact reading for the MJX image.
- Runtime/backend/frontend quality gates and production builds executed on Nebius pass; static
  OpenSpec validation may also be run on the host because it executes no project workload code.
- A GitHub or other third-party runner has not been used as a substitute for any Nebius preparation
  attestation; external CI is informational unless it dispatches the workload to Nebius.
- The CPU orchestration/builder is stopped whenever no active build, campaign-control, or verification
  process needs it.

The command is executed on the Nebius orchestration VM:

```bash
uv run python -m sim2policy.showcase_campaign implementation-gate \
  --matrix sim2policy/configs/showcase_training_matrix.yaml
```

Required result: exit 0 and `decision=PASS`. Any `SKIP`, warning-only substitute, missing test, or
mutable image tag is a failure.

## 5. Campaign initialization

1. Read `ARCHITECTURE.md`, `AGENTS.md`, this change's proposal/design/specs/tasks/runbook,
   `saas/API_RUNBOOK.md`, and the latest `IMPLEMENTATION_LOG.MD`.
2. On the host, use static Git/OpenSpec inspection to confirm the intended revision and preserve
   unrelated user work. Execute no project code.
3. Start the approved Nebius CPU orchestration VM, connect to it, and attest its instance ID/region.
   In its clean repository checkout run `git status --short --branch`; confirm `debug-portal` and the
   intended immutable revision. Stop on any dirty overlap or revision mismatch.
4. On the Nebius VM, inspect `openspec list` and run the implementation-complete gate.
5. Choose the campaign ID once. Use `gallery-result-YYYYMMDD-01`; increment the suffix only if that
   exact ID already belongs to a different matrix digest. Never reuse an ID for a changed plan.
6. Run `init`, then `status --format json`.
7. Confirm ordered examples are exactly:
   `reacher`, `halfcheetah`, `ant`, `hopper`, `walker2d`, `go1`, `g1`.
8. Run `handoff` and append its sanitized summary to `IMPLEMENTATION_LOG.MD`.

## 6. Global preflight before every paid attempt

Run `preflight` immediately before `plan`. It SHALL fail closed unless all checks pass:

### Repository and revision

- branch is `debug-portal`;
- Nebius orchestration checkout matches the intended reviewed revision and is clean;
- Nebius source commit equals the immutable image revision expected by the matrix;
- required Nebius-executed tests are successful; existing GitHub Actions status is inspected for
  repository/deployment health only and cannot replace a Nebius execution attestation;
- current instance metadata matches the approved Nebius orchestration VM and region;
- no command targets `main`.

### Infrastructure and credentials

- existing OpenTofu outputs resolve project, subnet, registry, artifact bucket, endpoint, region, and
  secret selectors without printing secret values;
- registry and artifact credentials are available through the existing configured path;
- the chosen preset is available in `eu-north1` and quota is sufficient;
- H100 is checked only for Go1/G1; CPU D3 is checked only for SB3;
- expected 100 GiB job disk and timeout match the matrix;
- preemptible is false.

If implementation needs an OpenTofu read, its shell must first establish both auth layers exactly as
documented in `AGENTS.md`. The CLI performs this check without persisting token output.

### Existing resource audit

- no unaccounted active Serverless AI campaign job exists;
- no unaccounted running H100, L40S, or CPU builder instance exists;
- no orphan campaign disk, public IP, or temporary security rule exists;
- the last attempt is `CLEANED` or this is the first attempt.

The runner may report an unexpected resource, but the lightweight agent may not delete something it
cannot prove belongs to this campaign. It stops with `NEEDS_HUMAN: UNACCOUNTED_RESOURCE`.

### Submission plan

`plan` must print all of the following before `submit` is legal:

- example, phase, seed, attempt number, base/extension status;
- exact non-tenant run ID and expected durable prefix;
- backend/module, immutable image tag and digest, config path and digest;
- effective total steps and checkpoint interval;
- platform, preset, disk, non-preemptible flag, hard timeout;
- training, selection, and final seed roles;
- parent checkpoint/run/digest for an extension or curriculum transition;
- required artifacts and final gate;
- maximum retries remaining;
- cleanup action;
- normalized plan digest;
- fully redacted provider command preview.

The agent compares this output to the applicable run card below. Any mismatch is exit 40 and no
submission.

For the two-phase G1 job, the plan declares both exact child prefixes: `RUN_ID-rough` is the final
candidate prefix and `RUN_ID-flat` is the diagnostic prefix used only when the prerequisite never
passes. Verification may resolve only those two plan-bound identities; fuzzy or unrelated cross-run
fallback remains prohibited.

## 7. Standard attempt loop

Use this loop for every base seed, extension, and G1 curriculum job:

1. `preflight` — require exit 0.
2. `plan --example EXAMPLE --seed SEED` — require exact run-card match; copy plan digest.
3. `submit ... --confirm-plan-digest DIGEST` — require exit 0 and a recorded remote ID. Never repeat
   immediately because output was slow; inspect `status` first.
4. `watch --poll-seconds 60 --until-terminal` — the CLI may remain active, but it writes a heartbeat
   every poll. If the calling environment yields, rerun the same command. Exit 10 means still active.
5. On provider terminal state, run `verify` even when training failed. Verification distinguishes
   durable checkpoint/evidence, finalization-only failure, and unusable failure.
6. Run `cleanup`. It verifies artifacts required for recovery/diagnosis, then stops/deletes campaign-
   owned chargeable compute and audits all resource classes.
7. Require `cleanup_state=PASS`. If not, stop before any retry or next job.
8. Run `status`; execute only its exact `next_command`.
9. Run `handoff` and append the sanitized summary to `IMPLEMENTATION_LOG.MD`.

Do not tail logs manually except when `handoff` instructs a human to diagnose a stopped campaign.
Normal progress is `effective_steps/current_budget`, last durable checkpoint, heartbeat age, provider
state, and artifact-finalization stage from structured status.

## 8. Failure and retry table

| Observed classifier | Automated action | Maximum | Stop condition |
| --- | --- | ---: | --- |
| `SUBMIT_NO_REMOTE_ID` | Re-query exact run name/idempotency key; submit same digest only if absent | 1 | unknown/duplicate mismatch -> human |
| `DUPLICATE_MATCHING_PLAN` | Adopt existing remote ID | 1 | any digest mismatch -> invariant failure |
| `QUEUE_OR_QUOTA` | No hardware substitution | 0 | human resolves capacity/quota |
| `FAILED_BEFORE_CHECKPOINT` | Identical retry after cleanup | 1 | second failure -> human |
| `FAILED_AFTER_COMPATIBLE_CHECKPOINT` | Resume exact image/config/run lineage | 1 | second failure or digest drift -> human |
| `FINALIZATION_ONLY_FAILURE` | Retry finalization from selected durable checkpoint | 1 | second failure -> human |
| `NUMERICAL_FAILURE` | Preserve evidence and stop | 0 | human/reviewed design required |
| `TIMEOUT_DURING_FINALIZATION` | Finalization-only retry if checkpoint and metrics are durable | 1 | missing evidence -> human |
| `ARTIFACT_CHECKSUM_FAILURE` | No promotion and no overwrite | 0 | human investigation required |
| `CLEANUP_FAILURE` | Block all further submissions | 0 | human completes/audits cleanup |
| `UNKNOWN_PROVIDER_STATE` | Submit nothing | 0 | human reconciles provider state |

An extension is not a retry. It is allowed only by the quality decision after all three base seeds.
A retry never changes the planned total steps.

## 9. Artifact verification contract

The `verify` command and every artifact parser it invokes execute on Nebius compute. The host receives
only the sanitized result envelope. `verify` SHALL check the exact curated prefix and reject
cross-run fallback. Required evidence is:

- terminal `status.json` with normalized success state;
- resolved configuration and its digest;
- runtime/framework versions and immutable image revision/digest;
- full training metrics and exact effective-step count;
- checkpoint inventory with steps and SHA-256 digests;
- selection evaluations with per-episode data and disjoint seeds;
- explicit selected-checkpoint record and ranking explanation;
- final 20-episode acceptance with per-episode metrics and hard/preferred results;
- Markdown report derived from the same structured metrics;
- native selected checkpoint and any files required to load it;
- initial, representative intermediate, selected, and final-step rollout media with exact labels;
- checksummed artifact manifest with no missing/unexpected critical objects;
- policy bundle whose internal inventory, digests, task identity, and selected checkpoint match;
- measured training/finalization duration, hardware, rate date, and cost inputs;
- sanitized public API fixture that passes current backend schema and isolation checks.

An artifact is not accepted merely because it exists. Size, checksum, content identity, and linkage to
the selected checkpoint must validate. The runner must not repair an old prefix in place.

## 10. Selection and extension algorithm

For Reacher, HalfCheetah, Ant, Hopper, Walker2D, and Go1:

1. Complete and clean all three base seeds in order 0, 7, 42.
2. Evaluate the retained checkpoint set on the selection seeds only.
3. Rank all checkpoints across all three seeds with the matrix rule.
4. Record the winning seed, step, checkpoint digest, metrics, and runner-up gap.
5. If the winner meets the preferred target, mark `EXTENSION_SKIPPED_QUALITY_MET`.
6. If it misses the preferred target, create exactly one continuation plan from the winner to the
   declared extension total. The parent digest must match the selected checkpoint.
7. Complete, verify, and clean the extension. Add its checkpoints to the candidate pool and rerank.
8. Run final acceptance exactly once on the selected checkpoint.
9. If hard floor and preferred target both pass, emit `ACCEPTED`.
10. If hard floor fails, emit `REJECTED_HARD_GATE` and leave unpublished.
11. If hard floor passes but preferred target fails, emit `NEEDS_HUMAN_QUALITY_TARGET`. Do not pin.

Selection must not look at final acceptance seeds. Final acceptance may not be repeated with a
different candidate because the first candidate was unlucky; that would turn the final set into a
selection set.

## 11. Robot run cards

These cards are the human-readable mirror of the matrix. The CLI output must match them exactly.

### 11.1 Reacher

- Example ID: `reacher`; canonical environment: `Reacher-v5`; backend: SB3 PPO.
- Hardware: `cpu-d3` / `8vcpu-32gb`; disk: 100 GiB; non-preemptible; timeout: 1 hour.
- Base seeds: 0, 7, 42; 1,000,000 effective steps each; checkpoint every 100,000.
- Selection: five distinct selection seeds, two episodes each; rank highest deterministic mean reward,
  then lower reward standard deviation, then earlier checkpoint.
- Hard floor: mean reward >= -10.
- Preferred target: mean reward >= -7.
- Extension: winner only, resume to 1,500,000 total steps; no second extension.
- Expected first-pass training time: approximately 6–8 minutes per seed.

### 11.2 HalfCheetah

- Example ID: `halfcheetah`; canonical environment: `HalfCheetah-v5`; backend: SB3 PPO.
- Hardware: `cpu-d3` / `8vcpu-32gb`; disk: 100 GiB; non-preemptible; timeout: 2 hours.
- Base seeds: 0, 7, 42; 3,000,000 effective steps each; checkpoint every 250,000.
- Selection: deterministic mean reward, lower standard deviation, earlier checkpoint.
- Hard floor: mean reward >= 1500.
- Preferred target: mean reward >= 2000.
- Extension: winner only, resume to 5,000,000 total steps.
- Expected first-pass training time: approximately 13 minutes per seed.

### 11.3 Ant

- Example ID: `ant`; canonical environment: `Ant-v5`; backend: SB3 PPO.
- Hardware: `cpu-d3` / `8vcpu-32gb`; disk: 100 GiB; non-preemptible; timeout: 3 hours.
- Base seeds: 0, 7, 42; 3,000,000 effective steps each; checkpoint every 250,000.
- Selection: mean reward, mean episode length, lower standard deviation, earlier checkpoint.
- Hard floor: mean reward >= 1000.
- Preferred target: mean reward >= 2500 and mean episode length >= 850.
- Extension: winner only, resume to 5,000,000 total steps.
- Expected first-pass training time: approximately 25 minutes per seed.

### 11.4 Hopper

- Example ID: `hopper`; canonical environment: `Hopper-v5`; backend: SB3 PPO.
- Hardware: `cpu-d3` / `8vcpu-32gb`; disk: 100 GiB; non-preemptible; timeout: 3 hours.
- Base seeds: 0, 7, 42; 5,000,000 effective steps each; checkpoint every 250,000.
- Selection: mean reward, mean episode length, lower standard deviation, earlier checkpoint.
- Hard floor: mean reward >= 1000.
- Preferred target: mean reward >= 1800 and mean episode length >= 500.
- Extension: winner only, resume to 8,000,000 total steps.
- Expected first-pass training time: approximately 24 minutes per seed.

### 11.5 Walker2D

- Example ID: `walker2d`; canonical environment: `Walker2d-v5`; backend: SB3 PPO.
- Hardware: `cpu-d3` / `8vcpu-32gb`; disk: 100 GiB; non-preemptible; timeout: 3 hours.
- Base seeds: 0, 7, 42; 5,000,000 effective steps each; checkpoint every 250,000.
- Selection: mean reward, full-horizon episode count, lower standard deviation, earlier checkpoint.
- Hard floor: mean reward >= 1800.
- Preferred target: mean reward >= 3500 and mean episode length = 1000.
- Extension: winner only, resume to 8,000,000 total steps.
- Expected first-pass training time: approximately 28 minutes per seed.

### 11.6 Go1

- Example ID: `go1`; canonical environment: `Go1JoystickFlatTerrain`; backend: MJX PPO.
- Hardware: `gpu-h100-sxm` / `1gpu-16vcpu-200gb`; disk: 100 GiB; non-preemptible;
  timeout: 2 hours.
- Base seeds: 0, 7, 42; 200,000,000 effective steps each; checkpoint every 10,000,000.
- Selection: full-horizon no-fall count, minimum velocity, mean length, mean velocity, reward.
- Hard floor: 20/20 episodes reach 1,000 steps without a fall and every episode is >= 0.5 m/s.
- Preferred target: same 20/20 stability, minimum >= 0.75 m/s, mean >= 0.9 m/s.
- Extension: winner only, resume to 300,000,000 total steps.
- Expected first-pass training time: approximately 25 minutes per seed, plus finalization.

### 11.7 G1 humanoid

- Example ID: `g1`; diagnostic identities: `G1JoystickFlatTerrain` and
  `G1JoystickRoughTerrain`; fresh canonical identities: `G1ForwardFlatTerrain` and
  `G1ForwardRoughTerrain`; backend: dedicated MJX recovery curriculum.
- Hardware: `gpu-h100-sxm` / `1gpu-16vcpu-200gb`; disk: 100 GiB; non-preemptible;
  failed sweep timeout: 90 minutes; full timeout: 5 hours. Read-only provider evidence proves the
  prior full flat/rough workload and finalization completed in 244 minutes; the earlier OOM/timeout
  inference was false.
- Authorization: `user_reviewed_rough_08_full_v2`, only campaign
  `gallery-g1-rough08-full-20260803-01`, one job, seed 0, zero retries/extensions/overrides.
- Seed: 0 only; fresh result ceiling: 450,000,000 effective steps across flat and rough phases.
- Fixed-forward contract: flat command `[1.0, 0.0, 0.0]` and rough command `[0.8, 0.0, 0.0]` at
  reset and every step through horizon 1,000; no zero-command branch, no effective command
  resampling, pushes disabled, unchanged reviewed PPO and reward settings.
- MJX phase requests are rounded down to whole PPO epoch quanta before submission, and provenance
  records requested and measured steps, so upstream batch rounding cannot exceed the ceiling.
- Superseded diagnostic path: the evaluation-only sweep reached its 90-minute provider timeout and
  wrote no durable eligibility report. Retain its provider record, infer no parent, submit no pilot,
  and never create a synthetic pilot gate.
- Brax phase-boundary contract: restore observation-normalizer, policy, and value parameters; record
  fresh seed-0 optimizer, learner-step, rollout-state, and PRNG initialization. Never call the pinned
  checkpoint an exact optimizer continuation.
- Fresh flat stage: from scratch, uninterrupted to the largest PPO epoch quantum at or below nominal
  200M—199,229,440 effective steps under the reviewed batch contract—with candidates every 25M.
  Gate only that derived final checkpoint at 10/10 horizon and minimum velocity >=0.4 m/s; earlier
  checkpoints are progression evidence and cannot become the transition parent.
- Flat transition: atomically record and verify exact object/path, step, digest, environments,
  image/config/matrix digests, measured spend, and remaining budget before rough PPO starts.
- Fresh rough stage: resume exact selected flat digest; spend all remaining steps up to the fixed
  450M total; candidates every 25M.
- Termination evidence: `horizon`, `torso_inversion`, `foot_foot_contact`, `foot_shin_contact`,
  `nan_state`, or `unknown_environment_done`; every non-horizon reason fails stability.
- Selection: full-horizon no-termination count, minimum velocity, mean length, mean velocity, reward.
- Hard floor: 20/20 rough-terrain episodes reach 1,000 steps without environment termination and
  every episode is >= 0.4 m/s.
- Preferred target: hard floor plus mean velocity >= 0.6 m/s.
- Extension: none. No retry, pilot, second job, seed, reward change, threshold change, or hardware
  comparison is authorized.
- Expected full completion: 3h50–4h15 end to end based on measured H100 throughput.

## 12. G1 reviewed rough-0.8 v2 state machine

The reviewed recovery is internally deterministic:

```text
RETAIN_FAILED_SWEEP_AND_V1_RESULT -> VERIFY_USER_REVIEWED_ROUGH_08_FULL_V2
  any mode/campaign/revision/image/matrix/seed/hardware/budget drift -> NEEDS_HUMAN
  exact reviewed tuple -> FRESH_FLAT_TRAIN_TO_QUANTIZED_200M

FRESH_FLAT_TRAIN_TO_QUANTIZED_200M -> FLAT_GATE_AT_DERIVED_FINAL_STEP
  fail -> FINALIZE_DIAGNOSTIC -> CLEAN -> NEEDS_HUMAN
  pass -> WRITE_AND_VERIFY_TRANSITION

WRITE_AND_VERIFY_TRANSITION -> FRESH_ROUGH_TRAIN_TO_TOTAL_450M
  -> RANK_ROUGH_CHECKPOINTS
  -> FINAL_ACCEPT_SELECTED
    hard+preferred pass -> ACCEPTED
    hard fail -> REJECTED
    hard pass/preferred fail -> NEEDS_HUMAN
```

The failed diagnostic sweep and terminal v1 result are retained evidence, never public candidates
or fabricated prerequisites. The fresh flat gait
prerequisite must include full-horizon commanded motion and no-termination stability; reward-only or
standing-only criteria are forbidden. The selection seeds are used for the fresh flat and rough
checkpoint gates.
Final seeds are not touched until one fresh rough checkpoint is chosen.

Training continues through the declared rough budget even after a promising checkpoint so the
campaign collects progression and may find a better checkpoint. Numerical divergence, provider
failure, or timeout are the only automatic early termination conditions after rough training begins.
Recovery finalization reads the immutable transition record and cannot re-run a flat gate or select a
different parent.

## 13. Exact campaign sequence

For each of the first six examples, run the standard attempt loop for seed 0, then 7, then 42. After
all three are verified and cleaned, run `select`. If its `next_command` is `extend`, run exactly that
one extension, verify, clean, and select again. Then run `accept`, verify the accepted record, and run
`audit-cloud` before moving on.

Sequence:

1. Reacher seeds 0/7/42 -> optional Reacher extension -> acceptance -> cleanup audit.
2. HalfCheetah seeds 0/7/42 -> optional extension -> acceptance -> cleanup audit.
3. Ant seeds 0/7/42 -> optional extension -> acceptance -> cleanup audit.
4. Hopper seeds 0/7/42 -> optional extension -> acceptance -> cleanup audit.
5. Walker2D seeds 0/7/42 -> optional extension -> acceptance -> cleanup audit.
6. Go1 H100 seeds 0/7/42 -> optional extension -> acceptance -> cleanup audit.
7. Retain the failed G1 diagnostic sweep and its clean terminal audit; submit no pilot.
8. Verify the exact `user_reviewed_rough_08_full_v2` tuple and submit one fresh G1 450M H100
   curriculum -> acceptance or terminal diagnostic -> cleanup audit.

Do not reorder to keep H100 warm. Serverless jobs and artifacts are the boundary; there is no
authorization to leave an instance running between examples.

## 14. Runtime envelope and monitoring expectations

Approximate first-pass wall time, including three base seeds but excluding extensions:

| Example | Approximate base campaign |
| --- | ---: |
| Reacher | 20–30 minutes |
| HalfCheetah | 40–55 minutes |
| Ant | 75–95 minutes |
| Hopper | 70–90 minutes |
| Walker2D | 85–105 minutes |
| Go1 | 75–100 minutes |
| G1 recovery | full 3h50–4h15 with a 5h timeout under the reviewed rough-0.8 v2 mode |
| **Sequential total** | **about 8–11 hours including the one full G1 result attempt** |

Queue delays or a single extension can add time. These estimates are not cancellation deadlines;
only the matrix timeout controls. A watcher reports at 60-second intervals. If no heartbeat is
recorded for five minutes while provider state is active, status becomes needs-human rather than
submitting a replacement.

## 15. Acceptance and promotion preparation

`accept` performs final evaluation and curation; it does not edit source. Required outcome for an
automatic public candidate is `hard_gate=true`, `preferred_target=true`, `artifacts=true`,
`public_fixture=true`, `provenance=true`, and `cleanup_state=PASS`.

For an accepted example:

1. Generate a deterministic acceptance record containing safe IDs/digests and measured evidence.
2. Verify the run ID is non-tenant and unique across cards.
3. Prepare a source diff replacing exactly that example's placeholder/current pin.
4. Run runtime/backend/frontend tests, production builds, and executable secret/large-file scanners
   on the Nebius CPU VM. The host may run only static `git diff --check` and OpenSpec validation.
5. Commit/push only on `debug-portal` after human review of the pin diff.
6. Use `gh` to inspect the relevant GitHub Actions run and failed logs.
7. Verify deployment health, then anonymous catalog/detail/media/download behavior on desktop and
   375px light/dark layouts.
8. Confirm there is no training control and signed-in tenant history/training remain unchanged.

If an example is rejected or needs human, leave its placeholder/current accepted pin untouched. The
next example may proceed only after cleanup passes; failure does not justify weakening its gate.

## 16. Cloud cleanup checklist

After every attempt, the CLI and agent must report each item explicitly:

- Serverless AI job terminal status and retained provider record;
- no active campaign job other than the one represented in state;
- campaign-owned VM stopped or deleted;
- CPU builder stopped when inactive;
- no campaign preparation or workload process executed on the shared host;
- every accepted executable result has a matching Nebius location attestation;
- no unaccounted H100/L40S/CPU VM running;
- no orphan campaign disk;
- no campaign-created public IP;
- no temporary security rule remaining;
- durable artifact prefix verified;
- SaaS row and artifact evidence retained;
- next submission blocked until all applicable checks are `PASS`.

Never delete an unexpected resource just because its name resembles the campaign. Report it for
human ownership verification.

## 17. Lightweight-agent handoff template

At interruption, completion, exit 30, or exit 40, run `handoff --format markdown`. The report must
contain exactly these sections and no secrets:

```markdown
## Campaign handoff
- Campaign ID:
- Matrix digest:
- Repository revision / image digests:
- Current example / seed / attempt:
- State and reason code:
- Remote job ID and provider state:
- Effective steps / last durable checkpoint digest:
- Verified artifacts / missing artifacts:
- Selection or acceptance result:
- Cleanup audit result:
- Retries and extensions already consumed:
- Exact next command, or NEEDS_HUMAN:
- Safe operator note:
```

The agent does not add speculative diagnosis. If `next_command` is absent, it stops.

## 18. Final campaign completion criteria

The campaign is complete when every example is in one of these states:

- `ACCEPTED_AND_PIN_READY`: fresh run passes hard and preferred gates, evidence and cleanup pass;
- `REJECTED`: hard gate failed after the exact bounded plan;
- `NEEDS_HUMAN`: preferred target, infrastructure, invariant, or cleanup requires a reviewed choice.

“All seven jobs completed” is not completion. Public success is the subset with accepted immutable
evidence. The final handoff reports accepted pins, unpublished examples, total measured runtime/cost,
all consumed retries/extensions, and a clean cloud audit.
