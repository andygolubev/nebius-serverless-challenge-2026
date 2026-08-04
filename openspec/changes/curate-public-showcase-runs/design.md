## Context

The public gallery has seven placeholders. Historical non-tenant artifacts establish useful baselines:

| Example | Historical result | Interpretation |
| --- | ---: | --- |
| Reacher | -7.779 mean reward at 300k | passes the -10 floor |
| HalfCheetah | 1672.368 at 1M | passes the 1500 floor, little margin |
| Ant | 2869.711 at 1M | strong reward, 895.6 mean episode length |
| Hopper | 1562.019 at 2M | passes the 1000 floor, moderate margin |
| Walker2D | 3812.003 at 2M | strong, full-length episodes |
| Go1 | 20/20 no-fall, 0.9653 m/s mean at 100M | strong locomotion baseline |
| G1 | 0/20 no-fall at 200M; about 763 mean steps | learns motion but fails durability |

The G1 H100 measurement is the planning anchor: 202.3424M effective steps took 5,510 seconds end to
end, including roughly 249 seconds of JIT and 5,105 seconds of PPO. Linear scaling puts 450M training
near 204 minutes; allowing a second environment compile, checkpoint evaluations, uploads, and final
rendering gives a realistic 3h50–4h15 completion window. Provider inspection later proved the full
flat/rough workload, evaluation, rendering, bundling, and upload completed in 244 minutes. The old
signal-kill/OOM inference was false, and the five-hour timeout has about 56 minutes of measured
margin.

The completed seed-0 G1 campaign invalidated two assumptions in the original run card. Its selected
46,202,880-step rough checkpoint achieved the required speed (minimum 0.7769 m/s, mean 0.8619 m/s)
but only 1/10 selection episodes and 0/20 final episodes completed the 1,000-step horizon; all 14
retained rough candidates achieved at most 1/10. This is a stability plateau, not evidence that the
same objective merely needs more steps. The actual rough PPO log also says it restored the
149,422,080-step flat checkpoint while recovery-generated provenance names the 99,614,720-step
checkpoint. Recovery had re-evaluated the flat gates and invented a new parent instead of preserving
the transition that training executed. Finally, the evaluator labeled every upstream environment
termination as `fall`, although pinned Playground v0.2.0 terminates G1 on torso inversion,
foot-foot contact, foot-shin contact, or a NaN state.

The training and acceptance command distributions also differ. Upstream G1 training samples x/y/yaw
commands, includes a 10 percent zero-command branch, and resamples after 500 control steps. Gallery
acceptance forces `[1.0, 0.0, 0.0]` without resampling for all 1,000 steps. The recovery experiment
therefore changes command distribution first while preserving the reviewed PPO and reward settings.
That isolates the most direct mismatch and keeps any later reward redesign evidence-driven.

The current generic submitter invokes only `train_sb3` or `train_mjx`; hosted entry points train and
finalize but always evaluate the final checkpoint. Neither is sufficient for a low-judgment campaign
operator. Implementation must precede paid execution.

Constraints are unchanged: work remains on `debug-portal`; public routes are anonymous and read-only;
tenant identities cannot be pinned; images/configs are immutable; bucket and registry secrets are
resolved from existing infrastructure; Serverless AI provider history is retained unless explicitly
reversed; every chargeable VM is stopped or deleted when its work ends. The shared host is not an
execution target: every executable preparation, test, build, import, smoke run, environment load,
artifact verifier, evaluator, renderer, trainer, finalizer, and campaign-runner process runs on
Nebius Cloud compute. The host is limited to source/planning edits, non-executing Git/OpenSpec
inspection, and authenticated control-plane/SSH commands whose payload executes in Nebius.

## Goals / Non-Goals

**Goals**

- Produce fresh, high-quality, independently accepted runs for all seven gallery examples.
- Give a lightweight agent an exact, resumable execution path with no hyperparameter or retry
  improvisation.
- Prefer robust final behavior over minimum spend while keeping experiments bounded.
- Select the best evaluated checkpoint across steps and seeds, not merely the latest checkpoint.
- Preserve honest initial/intermediate/selected/final progression and immutable provenance.
- End every branch in `ACCEPTED`, `REJECTED`, or `NEEDS_HUMAN`, with chargeable resources audited.
- Prove the execution location before every executable preparation or campaign transition and reject
  any attempt to run project workload code on the shared host.

**Non-goals**

- Launching jobs as part of this proposal.
- Exposing gallery training controls or arbitrary hyperparameters to tenants or public users.
- Automatically searching reward weights, architectures, or unbounded seeds after a declared plan
  fails.
- Treating a completed upload, high scalar reward, brief walking, or one lucky episode as success.
- Publishing the failed tenant G1 run or the unrelated custom-biped Stand Balance result.

## Decisions

### 0. Nebius Cloud is the only workload and preparation execution environment

The shared host is a control terminal, not a runner. It may edit files, inspect diffs/status, run the
OpenSpec CLI for planning validation, query GitHub/Nebius control planes, and establish SSH sessions.
It SHALL NOT install project dependencies or execute Python/Node training modules, lint/type/unit/
integration suites, frontend builds, Docker/BuildKit, image imports, MuJoCo/JAX/SB3 environments,
smoke tests, checkpoint evaluation, rendering, artifact verification, finalization, or campaign state
transitions.

Implementation creates or reuses the approved Nebius `cpu-d3` orchestration/builder VM in
`eu-north1`, normally `8vcpu-32gb` with a 300–500 GiB managed SSD. The exact `debug-portal` revision is
checked out there. It runs dependency setup, all CPU validation/test/build work, immutable image
construction, the campaign CLI, artifact verification, and cloud audits. GPU smoke/training executes
only in bounded Nebius Serverless AI jobs using the immutable image. The orchestration VM persists
the gitignored campaign state on its managed disk, uploads sanitized handoffs/evidence digests to the
approved durable location when required, and is stopped whenever no active preparation, campaign
control, or verification process needs it.

Every cloud-executed command records a location attestation containing provider instance/job ID,
region, image or host revision, start/end time, and command class, but no credentials. The campaign
preflight refuses an absent, local, ambiguous, or mismatched attestation. Results copied back to the
host are reports/digests only; native checkpoints, generated media, containers, and run artifacts
remain in the registry/private artifact bucket.

Alternative: run fast tests and campaign commands locally while reserving only training for Nebius.
Rejected because the operator explicitly requires all job preparation and execution to occur in
Nebius and because local dependency/runtime drift would weaken reproducibility.

### 1. A versioned campaign matrix is the sole source of execution choices

Implementation SHALL add `sim2policy/configs/showcase_training_matrix.yaml`. It contains one entry per
example and a schema version. Runtime code validates it before resolving infrastructure or submitting
a job. The campaign CLI prints a normalized plan plus SHA-256 digest; submission requires that digest.
The operator may choose a campaign ID, but may not override training steps, seeds, hardware, timeout,
acceptance, extension, or image/config revision from the CLI.

The initial matrix is:

| Example | Train budget per seed | Train seeds | Checkpoint interval | Preferred target | One allowed extension |
| --- | ---: | --- | ---: | --- | ---: |
| Reacher | 1M | 0, 7, 42 | 100k | mean reward >= -7 | best seed to 1.5M |
| HalfCheetah | 3M | 0, 7, 42 | 250k | mean reward >= 2000 | best seed to 5M |
| Ant | 3M | 0, 7, 42 | 250k | reward >= 2500 and mean length >= 850 | best seed to 5M |
| Hopper | 5M | 0, 7, 42 | 250k | reward >= 1800 and mean length >= 500 | best seed to 8M |
| Walker2D | 5M | 0, 7, 42 | 250k | reward >= 3500 and mean length = 1000 | best seed to 8M |
| Go1 | 200M | 0, 7, 42 | 10M | 20/20 no-fall, min >= 0.75 m/s, mean >= 0.9 m/s | best seed to 300M |
| G1 recovery | one reviewed fresh 450M total curriculum | 0 | see recovery curriculum | 20/20 no-termination, min >= 0.4 m/s, mean >= 0.6 m/s | none |

Hard publication floors remain Reacher -10, HalfCheetah 1500, Ant 1000, Hopper 1000, Walker2D 1800,
Go1 minimum 0.5 m/s in every full no-fall episode, and G1 minimum 0.4 m/s in every full episode with
no environment termination. Preferred targets control whether the single extension is used; they do
not replace the hard floor. A run below its hard floor is never accepted even when all artifacts
exist.

All non-G1 examples use three independent training seeds to reduce seed luck. Selection evaluations
use `[101, 151, 211, 271, 331]`, with two episodes per seed for ten episodes per checkpoint. Final
acceptance uses `[0, 1, 2, 3, 4]`, with four episodes per seed for twenty episodes. Training, selection,
and final seed roles are recorded separately; selection and final seeds may not overlap.

Alternative: let the operator edit environment variables for each launch. Rejected because an agent
could silently drift the experiment and make retries incomparable.

### 2. The campaign is a persisted, serialized state machine

The campaign CLI runs on the Nebius orchestration VM and writes only non-secret metadata beneath its
gitignored `.showcase-campaigns/<campaign-id>/`: normalized matrix digest, state JSON, append-only JSONL journal,
redacted plans, remote IDs, evidence digests, decisions, cleanup audits, and a handoff summary. Atomic
file replacement and a campaign lock prevent two operators from advancing the same campaign.

Per-attempt states are `PLANNED`, `PREFLIGHTED`, `SUBMITTED`, `RUNNING`, `FINALIZING`, `VERIFIED`,
`ACCEPTED`, `REJECTED`, `NEEDS_HUMAN`, and `CLEANED`. Exactly one remote training/finalization job may
be active for this campaign. Re-running a command reads state and either performs the one missing
transition or reports that the transition already completed.

The cloud-resident CLI owns polling, redaction, artifact verification, deterministic selection,
extension choice, and cleanup checks. A lightweight agent invokes documented commands through the
approved Nebius session and reports exit status. It never
parses live logs to invent a decision. Exit codes are stable: 0 completed requested transition; 10
remote work still active; 20 deterministic rejection recorded and campaign may advance; 30 human
decision required; 40 invariant/security/cleanup failure.

Alternative: a markdown checklist alone. Rejected because it cannot guarantee idempotency, seed
separation, one-active-job serialization, or safe resume after agent/context interruption.

### 3. SB3 gets more steps and multiple seeds on the validated CPU profile

Reacher, HalfCheetah, Ant, Hopper, and Walker2D retain their tested SB3 PPO configuration except for
server-owned total-step and checkpoint cadence changes declared in the matrix. Each run uses
`cpu-d3`, `8vcpu-32gb`, 100 GiB, non-preemptible capacity. GPU is not used: SB3 PPO is CPU-bound in
this stack, so a GPU would not improve policy quality. Result-first here means more seeds, more steps,
and checkpoint selection on a stable platform, not unnecessarily expensive hardware.

Timeouts are one hour for Reacher, two hours for HalfCheetah, and three hours each for Ant, Hopper,
and Walker2D. Recorded throughput implies approximate first-pass durations per seed of 6–8, 13, 25,
24, and 28 minutes respectively, excluding unusual queue delays. The timeouts intentionally include
provisioning and finalization margin.

For each example all three base seeds run sequentially. Checkpoints are ranked on the selection set.
If the leading checkpoint meets the preferred target, the extension is skipped. Otherwise only that
seed continues from its exact selected checkpoint to the declared extension total. There is exactly
one extension. Final acceptance runs on the best candidate after base runs plus any extension. If it
passes the hard floor but misses the preferred target after the extension, it remains an engineering
result but is not pinned automatically; state becomes `NEEDS_HUMAN`. This preserves the user's
quality preference instead of filling the gallery with a merely adequate result.

### 4. Go1 uses H100 directly and emphasizes robust locomotion

Go1 runs three non-preemptible 200M-step seeds on `gpu-h100-sxm` / `1gpu-16vcpu-200gb`, 100 GiB,
with a two-hour timeout and 10M checkpoint cadence. The strong historical 100M result shows the task
is solvable; the larger budget and three seeds give selection room for a showcase-quality rollout.
Checkpoint ranking is lexicographic: full-horizon no-fall episode count, minimum forward velocity,
mean episode length, mean velocity, then configured reward. If the best base checkpoint misses the
preferred target, only its seed resumes to 300M. Final acceptance retains the existing 20-episode,
1,000-step, no-fall, per-episode 0.5 m/s hard floor.

Alternative: L40S-first because it is cheaper. Rejected for this campaign because the operator
explicitly accepts a 3–4 hour training window and prioritizes predictable completion and result.

### 5. G1 recovery aligns training with acceptance under one reviewed direct-full authorization

The rejected G1 policy does not justify another identical joystick-command attempt. Fixed-forward
environment, transition, restore, telemetry, rendering, and one-update smoke validation completed on
Nebius. The subsequent all-checkpoint diagnostic sweep reached its reviewed 90-minute provider
timeout and produced no durable result because its serial evaluation workload was larger than the
timeout allowed. No pilot parent can therefore be claimed. The operator deliberately supersedes
that sweep and its dependent disposable pilot for the time-bounded result attempt and authorizes
exactly one fresh 450M campaign using `user_reviewed_direct_full_v1`.

This is not a generic bypass. The normalized matrix binds the sole campaign ID
`gallery-g1-direct-full-20260803-01`, one allowed job, seed 0, the fixed-forward identities, exact
149,422,080 flat and 300,318,720 rough executable budgets, one non-preemptible H100 with 100 GiB,
and a five-hour timeout. The plan additionally binds the exact immutable revision, image digest, and
matrix digest and declares zero retries, extensions, overrides, or second submissions. Any different
mode, campaign ID, seed, hardware, budget, or mutable identity fails before submission.

#### 5.1 Exact task and environment contract

Implementation adds server-owned `G1ForwardFlatTerrain` and `G1ForwardRoughTerrain` identities over
the pinned Playground v0.2.0 G1 flat/rough scenes. They preserve observation shape, action shape,
noise, reset randomization, physics, termination conditions, reward terms, and PPO settings, but
`sample_command` always returns `[1.0, 0.0, 0.0]`. Consequently the upstream 500-step resampling call
returns the same command, and the 10 percent zero-command branch is absent. Pushes remain disabled.

The recovery does not change reward coefficients, discounting, architecture, optimizer, batch shape,
or acceptance thresholds. Changing command distribution and reward shaping at once would make a
pass uninterpretable and a failure unactionable. If the fresh fixed-forward campaign fails, the
workflow stops at `NEEDS_HUMAN`; a later reward change requires another reviewed decision using the
recorded termination distribution.

#### 5.2 Termination taxonomy and superseded read-only checkpoint sweep

Evaluation records `horizon`, `torso_inversion`, `foot_foot_contact`, `foot_shin_contact`,
`nan_state`, or `unknown_environment_done`. When several conditions occur on one step, evidence
retains all causes and chooses a deterministic primary reason in the order NaN, torso inversion,
foot-foot, foot-shin, unknown. Every non-horizon reason remains a hard-gate failure; better labels do
not weaken acceptance.

The original recovery design required one evaluation-only H100 job to download retained flat
checkpoints from the rejected campaign and evaluate each under both `G1ForwardFlatTerrain` and
`G1ForwardRoughTerrain` using only selection seeds `[101, 151, 211, 271, 331]`, four episodes per
seed. The sweep never touches final seeds and cannot produce a public candidate. A pilot parent is
eligible only when its fixed-forward flat result has 20/20 full-horizon episodes, every episode has
mean velocity at least 0.4 m/s, and the pinned Brax checkpoint restores its complete supported tuple:
observation-normalizer parameters, policy parameters, and value parameters. Among eligible parents,
the rough zero-shot result ranks them by full-horizon count, mean episode length, minimum velocity,
mean velocity, mean reward, then earlier step. Rough success is diagnostic, not an eligibility
condition: requiring the unadapted flat parent to pass rough terrain would assume the result the
pilot exists to test. The job timed out after 90 minutes without its atomic final report. The
provider record and absence of durable eligibility evidence are retained. The sweep is not retried,
no eligible parent is inferred, and its dependent pilot is not submitted.

Pinned Brax 0.14.2 does not store or restore optimizer state, environment-step counters, rollout
state, or the learner PRNG in its PPO policy checkpoint. Every declared resume therefore restores
the supported tuple and deterministically initializes a fresh optimizer and rollout stream with
seed 0. The transition record states this explicitly and proves the restored tuple; it must not call
the operation an exact optimizer continuation. Implementing a custom full-state trainer is rejected
for this recovery because it would add a second, high-risk learning-system change to the
fixed-forward experiment.

#### 5.3 Superseded bounded pilot

The planned pilot would have resumed the exact selected diagnostic parent into
`G1ForwardRoughTerrain` with a 50M effective-step ceiling and 25M checkpoint cadence. Preflight
rounds down to the largest whole rough
PPO epoch quantum and, under the reviewed batch contract, asserts 46,202,880 executable steps. It
uses the normal locomotion selection seeds with two episodes per seed. The fresh campaign is unlocked
only when the best pilot checkpoint satisfies all of:

- at least 5/10 full-horizon episodes;
- mean episode length at least 900;
- minimum per-episode mean forward velocity at least 0.4 m/s;
- no NaN termination; and
- complete transition, checkpoint, runtime, and cleanup evidence.

This was deliberately a progress gate, not publication acceptance. It is materially stronger than
the failed baseline (1/10 and 823.4 mean steps) while allowing the full campaign to finish learning.
A failed or ambiguous pilot stops without a full run; the operator does not reinterpret videos or
training reward. Because the sweep produced no eligible-parent evidence, the pilot is superseded and
is not fabricated, retried, or counted as passed.

#### 5.4 One reviewed fresh fixed-forward result campaign

Under the exact `user_reviewed_direct_full_v1` authorization, the public candidate trains from
scratch rather than inheriting the failed sweep, a pilot, or the rejected campaign:

1. Train `G1ForwardFlatTerrain` uninterrupted from scratch to the largest whole PPO epoch quantum at
   or below the nominal 150M boundary. Under the reviewed batch contract, preflight must derive and
   assert 149,422,080 effective steps. Evaluate that exact final checkpoint on ten selection
   episodes and require 10/10 full-horizon episodes with every episode at least 0.4 m/s. Earlier
   checkpoints remain progression evidence and cannot become the transition parent. A failed gate
   stops before rough training.
2. Atomically publish a transition record naming the quantum-aligned flat object path, effective step,
   SHA-256 digest, source/target environment identities, config/matrix/image digests, and remaining
   budget. Download/resolve the parent once and verify the bytes and supported observation-normalizer,
   policy, and value tuple before invoking rough PPO. Record that optimizer, learner step, rollout
   state, and PRNG are freshly initialized at the phase boundary under seed 0.
3. Resume that checkpoint into `G1ForwardRoughTerrain`. Rough training receives
   `450M - measured_flat_training_steps`, aligned down again to PPO epoch quanta. Preflight records
   both the arithmetic remainder and executable rough request; their measured total may be below but
   can never exceed 450M. Preserve 25M candidates and train the declared remainder without using
   final seeds or manual cancellation.
4. Rank rough checkpoints by full-horizon no-termination count, minimum velocity, mean episode
   length, mean velocity, configured reward, then earlier checkpoint. Evaluate only the selected
   checkpoint on the disjoint final set.
5. Accept only if all 20 final episodes reach 1,000 steps, every episode averages at least 0.4 m/s,
   and mean velocity is at least 0.6 m/s. No threshold relaxation, second seed, reward mutation, or
   post-hoc final-set reselection is authorized.

The failed diagnostic path contributes no parent or policy bytes to the public result. The maximum
new training authorized by this emergency decision is one 450M result curriculum, executable as
149,422,080 flat plus 300,318,720 rough steps for 449,740,800 total.

#### 5.5 Reviewed rough-speed v2 after the terminal flat-gate failure

The v1 direct-full job is terminal and preserved. It trained the exact 149,422,080-step flat phase,
but only 8/10 selection episodes reached the horizon; therefore no transition was written and rough
training consumed zero steps. A generic diagnostic finalizer then evaluated reserved final seeds on
the failed flat checkpoint. Those episodes cannot authorize selection or publication and reveal a
failure-path isolation defect: a failed prerequisite must persist its selection evidence and return
without invoking the generic finalizer.

The operator's new explicit decision authorizes one fresh replacement campaign under the narrow mode
`user_reviewed_rough_08_full_v2`, bound only to campaign
`gallery-g1-rough08-full-20260803-01`. It preserves both prior Serverless AI jobs and permits one new
job, seed 0, zero retries/extensions/overrides, the same non-preemptible H100/100 GiB/five-hour shape,
and the same 450M ceiling. Flat uses invariant `[1.0, 0.0, 0.0]`; rough alone uses invariant
`[0.8, 0.0, 0.0]`. A 0.8 m/s command lowers rough-terrain impact and recovery demand while retaining
0.2 m/s headroom over the unchanged preferred mean threshold of 0.6 m/s. Choosing 0.6 would provide
no tolerance for tracking error; changing rewards or PPO at the same time would obscure causality.

The v2 phase split restores the demonstrated 200M-class flat preparation: nominal 200M quantizes to
199,229,440 effective steps. The rough remainder quantizes independently to 250,511,360, preserving
the same 449,740,800 total. This gives the prerequisite about 50M more steps than the failed v1 gate
while retaining more than 250M rough adaptation steps. The prior complete 200M-flat/250M-rough-class
workload trained, evaluated, rendered, bundled, and uploaded in 244 minutes, so a 300-minute provider
timeout remains evidence-based. The job is still accepted only at 20/20 rough horizons, every episode
at least 0.4 m/s, and mean at least 0.6 m/s.

Alternative: modify stability rewards immediately. Rejected for this iteration because the failed
run already used a -100 termination cost and strong orientation penalty; without exact termination
causes, another reward vector would be guesswork. Alternative: continue the rejected rough
checkpoint. Rejected because all 14 retained checkpoints plateaued below 2/10 full-horizon episodes.

### 6. Immutable provenance and best-checkpoint finalization precede execution

The runner only accepts images tagged with the exact source commit and resolved to a recorded digest.
It records the normalized config digest, image digest, parent checkpoint digest, effective steps,
checkpoint digest, framework/runtime versions, and campaign matrix digest. Resume is allowed only
when all of these inputs match the failed attempt.

For every cross-environment G1 resume, the durable transition record is written before the trainer
starts and the rough runtime record repeats the resolved input path, step, and digest. Verification
requires those values to agree with the actual checkpoint sidecar and the provider command. A
recovery finalizer consumes the recorded transition; it SHALL NOT re-run a flat gate, select a new
parent, or synthesize phase lineage. Missing or inconsistent transition evidence makes the run
diagnostic-only even when its policy metrics pass.

Hosted finalization must accept an explicit selected checkpoint. It evaluates and renders that
checkpoint, while retaining final-step metrics/media as honest progression evidence. Required
artifacts include status, resolved config, versions, metrics, report, native checkpoint, initial/
intermediate/selected/final media, checksummed manifest, and policy bundle. The artifact reader and
public serializer validate allowlisted real runtime schemas before a run can be pinned.

### 7. Recovery is bounded and mechanical

- Submission with no returned remote ID may be retried once with the same campaign key and run ID.
- A duplicate remote name is adopted only when its immutable plan digest matches.
- Queue/provisioning timeout, quota denial, unknown provider state, digest mismatch, numerical failure,
  or cleanup failure transitions to `NEEDS_HUMAN`; the agent does not change hardware or settings.
- A container failure after a durable compatible checkpoint may use `RESUME=remote` once. A failure
  before a checkpoint gets one identical retry. Further failure stops.
- If training and selected evidence are durable but finalization failed, retry finalization only; do
  not retrain.
- G1 finalization-only recovery must restore the immutable transition record and exact recorded
  parent. It may re-evaluate rough candidates but may not re-evaluate flat candidates to reconstruct
  a different transition.
- Preemptible capacity is prohibited for the result campaign.

### 8. Promotion is atomic per example and cleanup is mandatory

The normal order is Reacher, HalfCheetah, Ant, Hopper, Walker2D, Go1, then G1. Estimated sequential
first-pass wall time is roughly ten hours, dominated by G1, plus any single-seed extensions. An
accepted example may be pinned independently after its source change and tests pass; no failed card
is included just to reach seven.

After each terminal job the runner verifies durable evidence, then audits jobs, instances, disks,
public IPs, temporary security rules, and the reusable builder. Chargeable VMs are stopped or deleted.
Provider job records, SaaS rows, and S3 evidence are retained under the current policy. Promotion is
blocked until the cleanup audit passes.

### 9. Exact best-available G1 recording publication

After the replacement campaign also failed before rough training, the operator explicitly chose to
publish the strongest complete retained G1 recording today. The decision is limited to example
`g1-rough-terrain` and run `showcase-gallery-g1-20260801-16-g1-s0-rough`. Its manifest, checksums,
policy bundle, immutable image/config/matrix provenance, checkpoint, runtime/cost evidence, and six
videos were independently validated from durable storage. The selected 46,202,880-step rough
checkpoint walks at 0.8619 m/s mean and 0.7769 m/s minimum velocity, but completes 0/20 full-horizon
episodes and therefore remains below the locomotion threshold.

This is a verified recording exception, not an acceptance override. The public serializer retains
`success: false`, the actual aggregate values, and a below-task-threshold badge. It MUST NOT emit
`success: true`, change the acceptance evidence, lower a threshold, or make any other run eligible.
The exception is an exact server-owned tuple of example ID, run ID, canonical runtime environment,
and backend; any drift fails closed. All ordinary showcase pins remain accepted-only.

## Risks / Trade-offs

- **G1 rough-0.8 campaign fails**: preserve all milestone evidence, clean up, launch no other seed,
  reward vector, retry, or continuation; the operator may publish only the exact separately reviewed
  best-available recording with its below-threshold result visible.
- **Fixed-forward specialization reduces general joystick capability**: the public example is
  explicitly Walk Forward and its measured resolved configuration exposes this specialization; the
  tenant G1 joystick training card remains unchanged.
- **Three seeds multiply total runtime**: execution is sequential and resumable; quality and seed
  robustness are deliberately prioritized over minimum spend.
- **Preferred targets are too ambitious**: the one-extension rule bounds cost; missing a preferred
  target becomes `NEEDS_HUMAN` rather than silently publishing a marginal policy.
- **Selection overfits**: selection and final seed sets are disjoint and recorded; only the selected
  bounded candidate receives final acceptance.
- **Long G1 job dies during upload**: the measured 244-minute completed workload leaves about 56
  minutes inside the five-hour timeout, durable checkpoints permit exact supported-tuple resume, and
  finalization can be retried without retraining.
- **Agent interruption causes duplicate spend**: campaign lock, remote-name adoption, plan digests,
  and persisted state make every command idempotent.
- **Schema normalization leaks private fields**: the curator parses an allowlisted typed record and
  rejects unknown fields from public serialization by default.

## Migration Plan

1. Edit the matrix schema, campaign CLI/state machine, explicit-checkpoint finalizer, typed curation
   evidence, G1 termination taxonomy, fixed-forward environments, transition record, pilot gate, and
   fresh curriculum source without executing project code on the shared host.
2. Provision/start the Nebius CPU orchestration/builder VM; there, check out the exact revision,
   install dependencies, run all lint/type/unit/integration/frontend/build validation, build immutable
   SB3/MJX images, and push exact
   commit tags/digests, and stop the builder.
3. Retain the failed G1 evaluation-only sweep and terminal v1 direct-full job. Under the exact
   reviewed rough-0.8 v2 mode, submit one fresh 450M curriculum after the immutable Nebius
   validation/image/preflight gates pass.
4. Accept and pin examples independently only after hard and preferred quality gates, public-schema
   fixtures, and provenance checks pass.
5. Deploy through `debug-portal`, verify GitHub Actions with `gh`, then verify anonymous production
   cards, media, measured details, and unchanged tenant isolation.

Rollback is a source revert from a curated run ID to its placeholder or last accepted baseline. It
does not mutate or delete private artifacts.

## Open Questions

No operator choice remains. Exact rough-0.8 v2 values are declared above. Any missing immutable
revision/image/matrix binding, mismatched campaign ID, infrastructure output, quota, clean audit, or
runner capability is a preflight failure and must stop at `NEEDS_HUMAN`; a lightweight operator is
not authorized to fill the gap by guessing.
