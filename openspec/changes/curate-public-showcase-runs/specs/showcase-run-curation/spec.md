## ADDED Requirements

### Requirement: Nebius-only preparation and workload execution
The system and operator workflow SHALL execute every project preparation and workload process on
Nebius Cloud compute. This includes dependency installation, lint/type/unit/integration tests,
frontend production builds, Docker/BuildKit work, container health/import checks, simulation
environment construction, smoke runs, campaign-runner state transitions, artifact verification,
checkpoint selection/evaluation, rendering, training, and finalization. The shared host SHALL be
limited to source/planning edits, non-executing Git/OpenSpec inspection, and authenticated control-
plane or SSH invocation whose payload executes on Nebius. Each executable result SHALL carry a
sanitized Nebius location attestation. A GitHub, SaaS, or other control plane MAY dispatch or report
work, but a check used as campaign preparation evidence SHALL attest that its workload executed on
Nebius rather than on the shared host or a third-party hosted runner.

#### Scenario: Project command is invoked on the shared host
- **WHEN** preflight detects that a project test, build, import, simulation, campaign transition,
  evaluation, rendering, training, finalization, or artifact verifier would execute on the host
- **THEN** it fails before the command starts and reports `NEEDS_HUMAN: EXECUTION_LOCATION_INVALID`

#### Scenario: Nebius preparation result is accepted
- **WHEN** a test/build/smoke/verification result is used to advance the campaign
- **THEN** its evidence records a Nebius instance or job identity, region, immutable revision/image,
  command class, and timestamps without credentials

#### Scenario: Location attestation is absent or ambiguous
- **WHEN** the workflow cannot prove that executable preparation or workload ran in Nebius
- **THEN** the result is invalid and cannot satisfy preflight, acceptance, or promotion

#### Scenario: Third-party CI reports a passing workload check
- **WHEN** a GitHub-hosted or other non-Nebius runner reports a test, build, smoke, or artifact-
  verification success
- **THEN** that result may be informational but cannot satisfy a campaign preparation gate

### Requirement: Versioned result-first campaign matrix
The system SHALL maintain a server-owned, schema-validated campaign matrix for all seven showcase
examples. The matrix SHALL declare immutable config/image identity, training algorithm, effective-step
budget, checkpoint cadence, training seeds, disjoint selection and final seeds, hardware, disk,
timeout, hard acceptance floor, preferred quality target, ranking rule, and at most one extension.
Runtime overrides SHALL NOT weaken or alter those fields.

#### Scenario: Operator attempts an undeclared override
- **WHEN** a launch supplies a seed, step count, hardware, timeout, threshold, or config value that is
  not the normalized value in the reviewed matrix
- **THEN** preflight fails before infrastructure resolution or job submission

#### Scenario: Matrix is changed after planning
- **WHEN** the normalized matrix digest differs from the digest recorded for the campaign
- **THEN** submission and resume fail until a new reviewed campaign is explicitly initialized

### Requirement: Resumable serialized campaign execution
The campaign workflow SHALL persist non-secret state and an append-only journal, lock each campaign
against concurrent advancement, allow at most one active remote job, and make every transition
idempotent. It SHALL end each attempt in an explicit accepted, rejected, needs-human, or cleaned state
and SHALL expose stable machine-readable exit codes.

#### Scenario: Agent reruns a completed command
- **WHEN** the same transition command is invoked after its durable result was recorded
- **THEN** it reports the recorded result without submitting, retraining, overwriting evidence, or
  advancing a different attempt

#### Scenario: Another job is already active
- **WHEN** a submission is requested while any campaign attempt is submitted, running, or finalizing
- **THEN** the workflow rejects the submission and identifies the active non-secret campaign record

#### Scenario: Execution context is interrupted
- **WHEN** a new operator resumes a campaign from its state directory
- **THEN** the next command is derived from persisted provider/evidence state rather than memory or
  manual log interpretation

### Requirement: Fresh multi-seed SB3 result campaign
Reacher, HalfCheetah, Ant, Hopper, and Walker2D SHALL each train fresh seeds 0, 7, and 42 sequentially
on the validated `cpu-d3` `8vcpu-32gb` non-preemptible profile. Their base budgets SHALL be 1M, 3M,
3M, 5M, and 5M effective steps respectively, with checkpoint intervals of 100k for Reacher and 250k
for the other four. Only the best selected seed MAY receive the single declared extension to 1.5M,
5M, 5M, 8M, or 8M respectively.

#### Scenario: Base seed meets preferred quality
- **WHEN** the best selected checkpoint after the three base seeds meets the example's preferred
  target
- **THEN** the extension is skipped and that checkpoint proceeds to final acceptance

#### Scenario: Base seeds miss preferred quality
- **WHEN** the best selected checkpoint misses the preferred target
- **THEN** only that checkpoint's seed may resume once to the declared extension total

#### Scenario: Extended run remains marginal
- **WHEN** the extension completes without reaching the preferred target
- **THEN** the workflow records evidence, performs cleanup, and stops at needs-human without launching
  another seed, changing PPO settings, or automatically pinning the marginal result

### Requirement: Fresh H100 Go1 result campaign
Go1 SHALL train fresh seeds 0, 7, and 42 sequentially for 200M effective steps each on the
non-preemptible `gpu-h100-sxm` `1gpu-16vcpu-200gb` profile with 100 GiB disk, a two-hour timeout, and
10M checkpoints. If the best base checkpoint misses the preferred target, only that seed MAY resume
once to 300M. Final publication SHALL still require 20/20 1,000-step no-fall episodes and at least
0.5 m/s forward velocity in every episode.

#### Scenario: Go1 has a stable early checkpoint
- **WHEN** an earlier checkpoint outranks the final checkpoint by the declared locomotion rule
- **THEN** the earlier checkpoint is selected and finalization retains the final checkpoint as
  regression evidence rather than replacing the selection

#### Scenario: Go1 extension also misses quality
- **WHEN** the one 300M continuation does not satisfy the preferred 20/20 no-fall, minimum 0.75 m/s,
  and mean 0.9 m/s target
- **THEN** no further training is submitted automatically and the example enters needs-human

### Requirement: Bounded H100 G1 curriculum
G1 SHALL run at most one fresh seed-0, 450M-effective-step, non-preemptible H100 curriculum job with
a five-hour timeout. The job SHALL acquire a no-push flat-terrain gait by at most 200M steps, then
resume the selected flat checkpoint into no-push rough terrain for the remainder of the fixed total.
Final publication SHALL require 20/20 deterministic 1,000-step episodes without falls and at least
0.4 m/s measured forward velocity in every episode. The preferred mean SHALL be at least 0.6 m/s.

#### Scenario: Flat gait passes before 200M
- **WHEN** the deterministic gate at 100M or 150M demonstrates the declared full-horizon gait
  prerequisite
- **THEN** the job selects that checkpoint and assigns the remaining total-step budget to rough
  terrain without increasing the 450M ceiling

#### Scenario: Flat gait never passes
- **WHEN** no flat checkpoint passes by 200M
- **THEN** rough-terrain training is not started, diagnostics are finalized, cleanup runs, and the
  campaign stops at needs-human

#### Scenario: Rough checkpoint passes before final step
- **WHEN** a retained rough checkpoint outranks later checkpoints and passes final acceptance
- **THEN** that checkpoint is the selected public policy and later regression remains visible

#### Scenario: G1 exhausts its budget
- **WHEN** the 450M job fails the hard or preferred gate
- **THEN** the workflow launches no second seed, hardware comparison, reward change, or extra training
  without a new reviewed decision

### Requirement: Disjoint deterministic checkpoint selection
The workflow SHALL evaluate candidate checkpoints on selection seeds `[101, 151, 211, 271, 331]`
and SHALL reserve final seeds `[0, 1, 2, 3, 4]` for the selected checkpoint's 20-episode acceptance.
Locomotion ranking SHALL be lexicographic by full-horizon no-fall count, minimum forward velocity,
mean episode length, mean velocity, then configured reward. SB3 ranking SHALL use its configured
deterministic task score with declared stability tie-breakers. Final-step status SHALL confer no
ranking preference.

#### Scenario: Seed sets overlap
- **WHEN** any selection evaluation uses a seed reserved for final acceptance or vice versa
- **THEN** the evidence record is invalid and cannot be promoted

#### Scenario: Reward and stability disagree
- **WHEN** a locomotion checkpoint has higher reward but fewer full-horizon no-fall episodes
- **THEN** the more stable checkpoint ranks higher

#### Scenario: Training regresses
- **WHEN** a later evaluated checkpoint performs worse than a retained earlier checkpoint
- **THEN** both records remain in progression evidence and the selected checkpoint is determined by
  the declared ranking rule

### Requirement: Immutable curated acceptance evidence
A run SHALL be promotable only when its matrix digest, immutable image/config/checkpoint provenance,
selected-checkpoint evaluation, measured runtime/cost, sanitized resolved configuration, runtime
versions, report, native checkpoint, labeled progression media, checksummed manifest, and policy
bundle all validate and its normalized task success is true. Historical passing runs MAY be used as
baselines or explicit rollback targets but SHALL NOT replace a fresh campaign attempt silently.

#### Scenario: Artifact-complete run misses its gate
- **WHEN** all expected objects exist but the hard task gate is false
- **THEN** the run remains diagnostic evidence and is ineligible for public pinning

#### Scenario: Preferred quality is achieved
- **WHEN** a fresh selected checkpoint passes both its hard floor and preferred target with complete
  immutable evidence
- **THEN** the curator emits a deterministic accepted record eligible for the example's source pin

#### Scenario: Real runtime schema is ambiguous
- **WHEN** canonical environment identity, `success.met`, selected checkpoint, measured cost/runtime,
  or any public allowlisted field cannot be normalized unambiguously
- **THEN** curation fails closed before the run ID is changed in source

### Requirement: Bounded mechanical recovery
The workflow SHALL use fixed recovery rules: retry a submission with no remote ID once under the same
idempotency key; adopt a duplicate name only when its plan digest matches; retry an identical run at
most once before a durable checkpoint; resume once only from a compatible durable checkpoint; and
retry finalization without retraining when training evidence is already durable. Preemptible capacity
and undeclared fallback hardware SHALL be prohibited.

#### Scenario: Finalization fails after training
- **WHEN** the selected checkpoint and training evidence are durable but rendering, evaluation upload,
  manifest construction, or bundle publication fails
- **THEN** the workflow retries finalization only and does not spend steps retraining the policy

#### Scenario: Resume inputs drift
- **WHEN** image, matrix, config, parent checkpoint, or destination identity differs from the failed
  attempt
- **THEN** resume is rejected and the state becomes needs-human

#### Scenario: Provider state is unknown
- **WHEN** the runner cannot prove whether a submission exists or whether it is terminal
- **THEN** it submits nothing further and records a needs-human blocker

### Requirement: Cloud preflight, budget, and cleanup
Before every paid attempt the workflow SHALL verify `debug-portal`, Nebius-executed quality-gate
attestations, immutable images, infrastructure outputs, registry/artifact access, quota, exact
redacted command, timeout,
expected durable prefix, and absence of unintended active campaign compute. After terminal evidence
is durable it SHALL stop or delete every chargeable VM and audit jobs, instances, disks, public IPs,
temporary security rules, and builder state. Provider history, SaaS rows, and S3 evidence SHALL be
retained under the current policy.

#### Scenario: Preflight finds an active unrelated resource
- **WHEN** the cloud audit finds a potentially chargeable instance or job not accounted for by the
  current campaign state
- **THEN** submission stops for human reconciliation rather than assuming ownership

#### Scenario: Paid attempt terminates
- **WHEN** training/finalization reaches success or failure and required evidence has been inspected
- **THEN** cleanup executes before any next example is submitted

#### Scenario: Cleanup cannot be proven
- **WHEN** a chargeable resource cannot be stopped/deleted or the audit result is incomplete
- **THEN** promotion and subsequent submissions remain blocked

### Requirement: Safe independent promotion
Each example SHALL be promoted independently only from a fresh accepted non-tenant run. Promotion
SHALL replace exactly that example's placeholder or previous accepted pin, run strict runtime/backend/
frontend/OpenSpec validation, deploy only through `debug-portal`, and verify the anonymous public
surface. A failed example SHALL remain unpublished without blocking already accepted cards.

#### Scenario: Six examples pass and G1 fails
- **WHEN** six fresh campaigns produce accepted records and G1 stops at needs-human
- **THEN** only the six accepted examples may be pinned and G1 remains unpublished

#### Scenario: Candidate run identity is tenant-shaped
- **WHEN** a proposed pin matches a tenant job identity or resolves through a tenant-owned path
- **THEN** source update and public resolution are rejected regardless of evaluation quality
