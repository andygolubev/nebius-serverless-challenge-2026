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
rendering gives a realistic 3h50–4h15 completion window. The job timeout is therefore five hours so
successful training is not killed while finalizing.

The current generic submitter invokes only `train_sb3` or `train_mjx`; hosted entry points train and
finalize but always evaluate the final checkpoint. Neither is sufficient for a low-judgment campaign
operator. Implementation must precede paid execution.

Constraints are unchanged: work remains on `debug-portal`; public routes are anonymous and read-only;
tenant identities cannot be pinned; images/configs are immutable; bucket and registry secrets are
resolved from existing infrastructure; Serverless AI provider history is retained unless explicitly
reversed; every chargeable VM is stopped or deleted when its work ends.

## Goals / Non-Goals

**Goals**

- Produce fresh, high-quality, independently accepted runs for all seven gallery examples.
- Give a lightweight agent an exact, resumable execution path with no hyperparameter or retry
  improvisation.
- Prefer robust final behavior over minimum spend while keeping experiments bounded.
- Select the best evaluated checkpoint across steps and seeds, not merely the latest checkpoint.
- Preserve honest initial/intermediate/selected/final progression and immutable provenance.
- End every branch in `ACCEPTED`, `REJECTED`, or `NEEDS_HUMAN`, with chargeable resources audited.

**Non-goals**

- Launching jobs as part of this proposal.
- Exposing gallery training controls or arbitrary hyperparameters to tenants or public users.
- Automatically searching reward weights, architectures, or unbounded seeds after a declared plan
  fails.
- Treating a completed upload, high scalar reward, brief walking, or one lucky episode as success.
- Publishing the failed tenant G1 run or the unrelated custom-biped Stand Balance result.

## Decisions

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
| G1 | 450M total curriculum | 0 | see curriculum | 20/20 no-fall, min >= 0.4 m/s, mean >= 0.6 m/s | none |

Hard publication floors remain Reacher -10, HalfCheetah 1500, Ant 1000, Hopper 1000, Walker2D 1800,
Go1 minimum 0.5 m/s in every full no-fall episode, and G1 minimum 0.4 m/s in every full no-fall
episode. Preferred targets control whether the single extension is used; they do not replace the hard
floor. A run below its hard floor is never accepted even when all artifacts exist.

All non-G1 examples use three independent training seeds to reduce seed luck. Selection evaluations
use `[101, 151, 211, 271, 331]`, with two episodes per seed for ten episodes per checkpoint. Final
acceptance uses `[0, 1, 2, 3, 4]`, with four episodes per seed for twenty episodes. Training, selection,
and final seed roles are recorded separately; selection and final seeds may not overlap.

Alternative: let the operator edit environment variables for each launch. Rejected because an agent
could silently drift the experiment and make retries incomparable.

### 2. The campaign is a persisted, serialized state machine

The campaign CLI writes only non-secret metadata beneath gitignored
`.showcase-campaigns/<campaign-id>/`: normalized matrix digest, state JSON, append-only JSONL journal,
redacted plans, remote IDs, evidence digests, decisions, cleanup audits, and a handoff summary. Atomic
file replacement and a campaign lock prevent two operators from advancing the same campaign.

Per-attempt states are `PLANNED`, `PREFLIGHTED`, `SUBMITTED`, `RUNNING`, `FINALIZING`, `VERIFIED`,
`ACCEPTED`, `REJECTED`, `NEEDS_HUMAN`, and `CLEANED`. Exactly one remote training/finalization job may
be active for this campaign. Re-running a command reads state and either performs the one missing
transition or reports that the transition already completed.

The CLI owns polling, redaction, artifact verification, deterministic selection, extension choice,
and cleanup checks. A lightweight agent runs documented commands and reports exit status. It never
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

### 5. G1 is one bounded 450M H100 curriculum, not another flat 200M repeat

G1 uses one non-preemptible H100 job, seed 0, 100 GiB, and a five-hour timeout. A dedicated hosted
curriculum entry point keeps both stages in one allocation and produces one provenance chain.

1. Start `G1JoystickFlatTerrain` from scratch with pushes disabled and the reviewed upstream PPO
   contract: 8,192 environments, privileged critic, 20-step unroll, 32 minibatches, four updates,
   entropy cost 0.005, and the existing action/observation/reward contract.
2. Save candidates at least every 25M steps; run flat gait gates at 100M, 150M, and 200M. The gate is
   deterministic full-horizon commanded locomotion on the selection set, not reward alone.
3. Transition as soon as a gate passes. If none passes by 200M, stop training, finalize diagnostics,
   clean up, and set `NEEDS_HUMAN`; rough training is prohibited because there is no gait to harden.
4. Resume the selected flat checkpoint into no-push rough terrain. The rough stage receives all
   remaining steps from the fixed 450M total, so an early flat pass yields a longer rough stage.
   Preserve candidates every 25M and evaluate milestone candidates without deleting regressions.
5. Rank rough checkpoints by full-horizon no-fall count, minimum velocity, mean episode length, mean
   velocity, then reward. Evaluate the selected checkpoint on the disjoint final set.
6. Accept only if all 20 final episodes run 1,000 steps without falling and each achieves at least
   0.4 m/s. The preferred mean is at least 0.6 m/s. There is no automatic second 450M seed or
   post-hoc reward tuning.

The selected checkpoint may precede 450M. The job still finishes its bounded budget unless a
numerical/infrastructure failure occurs; checkpoint selection prevents later regression from erasing
an earlier good policy. The runner never cancels merely because an intermediate metric looks weak.

Alternative: continue a failed 200M rough checkpoint to 450M. Rejected because the policy has not
demonstrated a stable flat gait and two accelerators converged to the same fall pattern.

### 6. Immutable provenance and best-checkpoint finalization precede execution

The runner only accepts images tagged with the exact source commit and resolved to a recorded digest.
It records the normalized config digest, image digest, parent checkpoint digest, effective steps,
checkpoint digest, framework/runtime versions, and campaign matrix digest. Resume is allowed only
when all of these inputs match the failed attempt.

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

## Risks / Trade-offs

- **G1 still fails after 450M**: preserve all milestone evidence, clean up, leave G1 unpublished, and
  require a reviewed follow-up for a reward/task redesign or second seed.
- **Three seeds multiply total runtime**: execution is sequential and resumable; quality and seed
  robustness are deliberately prioritized over minimum spend.
- **Preferred targets are too ambitious**: the one-extension rule bounds cost; missing a preferred
  target becomes `NEEDS_HUMAN` rather than silently publishing a marginal policy.
- **Selection overfits**: selection and final seed sets are disjoint and recorded; only the selected
  bounded candidate receives final acceptance.
- **Long G1 job dies during upload**: five-hour timeout includes margin, durable checkpoints permit
  exact resume, and finalization can be retried without retraining.
- **Agent interruption causes duplicate spend**: campaign lock, remote-name adoption, plan digests,
  and persisted state make every command idempotent.
- **Schema normalization leaks private fields**: the curator parses an allowlisted typed record and
  rejects unknown fields from public serialization by default.

## Migration Plan

1. Implement and test the matrix schema, campaign CLI/state machine, explicit-checkpoint finalizer,
   typed curation evidence, and G1 curriculum locally; launch nothing.
2. Build immutable SB3/MJX images on the CPU builder, run increasing-cost image/smoke gates, push exact
   commit tags/digests, and stop the builder.
3. Execute the detailed runbook sequentially. Each job must verify artifacts and cleanup before the
   next submission.
4. Accept and pin examples independently only after hard and preferred quality gates, public-schema
   fixtures, and provenance checks pass.
5. Deploy through `debug-portal`, verify GitHub Actions with `gh`, then verify anonymous production
   cards, media, measured details, and unchanged tenant isolation.

Rollback is a source revert from a curated run ID to its placeholder or last accepted baseline. It
does not mutate or delete private artifacts.

## Open Questions

None for campaign execution. Any missing immutable image, infrastructure output, quota, or runner
capability is a preflight failure and must stop at `NEEDS_HUMAN`; a lightweight operator is not
authorized to fill the gap by guessing.
