## ADDED Requirements

### Requirement: Immutable curated-run inventory
The system SHALL maintain a reviewable inventory mapping each public example to exactly one
non-tenant curated run identity and its immutable runtime image, resolved configuration digest,
checkpoint digest, evaluation schema/version, artifact-manifest digest, and acceptance timestamp.
The inventory MUST reject tenant-shaped job identities, placeholders, mutable image tags, duplicate
run identities, and evidence whose declared example does not match the inventory key.

#### Scenario: Passing source run is inventoried
- **WHEN** an operator audits a non-tenant source run whose identity, immutable runtime, resolved
  configuration, checkpoint, evaluation, and artifact digests all agree
- **THEN** the curator emits a deterministic acceptance record eligible for source review

#### Scenario: Tenant job is offered for curation
- **WHEN** an operator supplies a tenant-shaped job ID, tenant artifact prefix, or run carrying
  tenant-owned robot/setup evidence
- **THEN** the curator rejects it before reading or copying any artifact into the public inventory

#### Scenario: Provenance is incomplete or mutable
- **WHEN** the source run omits a required digest/revision or records a mutable runtime reference
- **THEN** the curator rejects it and reports the missing provenance without inventing a value

### Requirement: Existing evidence before retraining
Before submitting a training job for an example, the curation workflow SHALL enumerate and validate
retained non-tenant acceptance runs and SHALL reuse a passing run when its provenance, evaluation,
artifact, and public-schema gates remain valid. It MUST NOT retrain an identical accepted
configuration merely to make every public run recent or visually uniform.

#### Scenario: Retained run still passes
- **WHEN** a retained source run passes the current integrity, success, progress, and compatibility
  gates
- **THEN** it is eligible for promotion without creating a new training job

#### Scenario: Retained run lacks derived progress evidence
- **WHEN** a passing retained source has its final checkpoint and artifacts but lacks the required
  structured progression record
- **THEN** the workflow may run bounded evaluation/finalization into a new deterministic curated
  prefix without modifying the source prefix or repeating policy training

### Requirement: Curated acceptance gate
A run SHALL be promotable only when its predeclared task success is true; its deterministic
multi-seed evaluation, selected checkpoint, measured runtime/cost inputs, safe resolved
configuration, runtime versions, required media, native checkpoint, report, checksummed manifest,
and policy bundle all validate; and the public API fixture derived from it passes the current
showcase schema. Artifact completion or scalar reward improvement alone SHALL NOT qualify.

#### Scenario: Complete passing evidence is promoted
- **WHEN** every acceptance input validates and the normalized task result is successful
- **THEN** the curator returns an accepted record containing exact digests and the run becomes
  eligible to replace that example's placeholder

#### Scenario: Completed policy misses its task threshold
- **WHEN** a run publishes every required artifact but any final evaluation episode violates the
  example's configured all-episode locomotion gate, or an aggregate SB3 threshold is not met
- **THEN** the run remains diagnostic evidence and is not eligible for public pinning

#### Scenario: Public-schema compatibility fails
- **WHEN** integrity checks pass but canonical environment identity, success schema, executed
  configuration, measured cost/runtime, progress metadata, or public serialization is ambiguous
- **THEN** the curator fails closed before source pinning

### Requirement: Selected-checkpoint evidence
For each curated run the workflow SHALL evaluate initial, intermediate, and candidate checkpoints
under deterministic selection settings, record exact step/digest/metrics for each, select a policy
using the task-specific success measures rather than training reward alone, and run final acceptance
on a seed set distinct from selection. A final-step checkpoint SHALL have no automatic preference
over an earlier checkpoint.

#### Scenario: Earlier locomotion checkpoint is more stable
- **WHEN** an earlier G1 checkpoint has more full-horizon no-fall episodes than the final checkpoint
- **THEN** selection ranks the earlier checkpoint higher and records why it was selected

#### Scenario: Selection and acceptance seeds overlap
- **WHEN** a curation record uses any final acceptance seed while choosing among candidate
  checkpoints
- **THEN** the record is rejected as overfit and cannot be promoted

#### Scenario: Training regresses
- **WHEN** an intermediate or later evaluated checkpoint performs worse than its predecessor
- **THEN** the progress record retains and labels the regression rather than replacing or hiding it

### Requirement: Bounded G1 convergence ladder
G1 curation SHALL proceed in increasing-cost phases: retained no-push checkpoint sweep, a bounded
flat-terrain gait prerequisite only if needed, a bounded no-push rough-terrain fine-tune only after
the flat gait passes, and one frozen fresh acceptance run. The final gate SHALL remain 20
deterministic episodes of 1,000 steps with at least 0.4 m/s measured forward velocity and no fall in
every episode. The workflow MUST NOT substitute the failed 25M tenant run, lower the velocity,
shorten the horizon, reduce evaluation breadth, or relabel standing/short motion as walking.

#### Scenario: Retained checkpoint passes
- **WHEN** a retained no-push checkpoint passes the unchanged full G1 gate
- **THEN** the workflow promotes that checkpoint through finalization and starts no new training

#### Scenario: Flat gait prerequisite fails
- **WHEN** the bounded flat-terrain phase cannot sustain commanded walking for the configured full
  horizon
- **THEN** rough-terrain fine-tuning is not started and G1 remains unpublished

#### Scenario: Rough-terrain curriculum passes
- **WHEN** the flat prerequisite passes and a selected rough-terrain checkpoint passes the unchanged
  final acceptance set with complete artifacts
- **THEN** its curation record includes both phase configurations and the parent checkpoint digest

#### Scenario: Budget is exhausted without a pass
- **WHEN** the predeclared candidate, GPU-hour, dollar, or wall-time ceiling is reached before G1
  passes
- **THEN** the workflow stops, preserves diagnostics, leaves the G1 placeholder in source, and
  requires a new reviewed change before further paid work

### Requirement: Evidence-based accelerator selection
Evaluation and pilot work SHALL use the cheapest validated accelerator that fits. H100 SHALL be
used after L40S only when an identical frozen workload has a predeclared, measured L40S capacity or
wall-time failure, or when a separately approved deadline justifies the higher cost. A policy-
quality failure on L40S SHALL NOT be called a hardware failure unless the identical H100 run passes.

#### Scenario: L40S candidate passes within bounds
- **WHEN** the frozen workload passes on L40S within its declared timeout and resource bounds
- **THEN** L40S is selected and no H100 duplicate is launched

#### Scenario: H100 is claimed as required
- **WHEN** the card or acceptance record names H100 as required
- **THEN** the record contains the predeclared L40S gate, its measured failure, and the identical
  passing H100 evidence

### Requirement: Cloud resource budget and cleanup
Before every paid phase the operator record SHALL state the immutable image/config, exact command
source, platform/preset, timeout, maximum candidate count, GPU-hour/dollar ceiling, expected durable
prefix, and cleanup action. After terminal evidence is durable, the workflow SHALL stop or delete
every chargeable VM and SHALL audit AI jobs, instances, disks, public IPs, and temporary security
rules. It SHALL preserve SaaS rows, S3 evidence, and provider history when the current retention
instruction requires it.

#### Scenario: Paid phase completes
- **WHEN** a curation evaluation or training phase reaches a terminal outcome and required evidence
  has been checked
- **THEN** chargeable instances are stopped/deleted immediately and the audit result is recorded

#### Scenario: Cleanup cannot complete
- **WHEN** a required instance or other chargeable resource cannot be stopped or deleted
- **THEN** promotion pauses and the blocker plus next safe cleanup action is recorded

