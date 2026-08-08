# durable-run-artifacts Specification

## Purpose
Make every training run's outputs durable and resumable: a stable per-run local/S3 artifact
layout, endpoint-configurable synchronization with bounded retries, complete-before-publish
checkpoint semantics, and explicit compatibility-checked resumption from the latest checkpoint.
The status lifecycle and artifact manifest that APIs read from the same tree are specified in
`run-state-artifacts`.

## Requirements
### Requirement: Stable per-run artifact layout
The system SHALL write each run beneath a unique local run directory and SHALL map `checkpoints`, `tensorboard`, `videos`, and `report` subdirectories to the same subpaths beneath a configurable S3-compatible run prefix.

#### Scenario: Run paths are created
- **WHEN** a new run ID is initialized
- **THEN** local artifact directories are created and their remote object keys resolve beneath only that run ID

#### Scenario: Unsafe run identity is supplied
- **WHEN** a run ID or prefix attempts path or object-key traversal
- **THEN** the system rejects it before reading or writing artifacts

### Requirement: Endpoint-configurable synchronization
The system SHALL synchronize artifacts through boto3 using configurable bucket, prefix, region, and endpoint settings, SHALL use the standard credential provider chain, and SHALL support a local-only mode when remote storage is not configured.

#### Scenario: Periodic and final sync succeeds
- **WHEN** storage is configured and training produces checkpoints or logs
- **THEN** periodic sync uploads completed artifacts and normal completion uploads all required final artifacts to their corresponding run prefix

#### Scenario: Local-only development run
- **WHEN** no object-storage destination is configured and local-only mode is selected
- **THEN** the workflow completes using the local run directory without attempting a remote connection

### Requirement: Completed checkpoint publication
The system SHALL upload a checkpoint completely before publishing it as the latest resumable checkpoint and SHALL include backend, environment, training step, and compatibility metadata in the latest-checkpoint record.

#### Scenario: Upload is interrupted
- **WHEN** a checkpoint object upload fails before completion
- **THEN** the latest-checkpoint record continues to reference the preceding completed checkpoint

### Requirement: Explicit checkpoint resumption
The system SHALL support an explicit resume mode that discovers the latest completed checkpoint, validates it against the selected backend, environment, and configuration compatibility rules, downloads it, and continues from its recorded progress.

#### Scenario: Compatible checkpoint exists
- **WHEN** resume mode is requested for a run with a compatible latest checkpoint
- **THEN** training restores that checkpoint and continues without restarting the progress counter

#### Scenario: Latest checkpoint is incompatible
- **WHEN** resume mode finds a checkpoint from another backend, environment, or incompatible configuration
- **THEN** the command exits with a compatibility diagnostic before training

### Requirement: Observable storage failures
The system MUST retry transient synchronization failures with bounded backoff, MUST retain available local artifacts, and MUST fail normal completion when required final artifacts cannot be made durable.

#### Scenario: Periodic sync is temporarily unavailable
- **WHEN** a transient remote error occurs during periodic sync
- **THEN** the system retries within configured bounds, records degraded sync status if retries are exhausted, and retains the local files

#### Scenario: Required final upload fails
- **WHEN** training completes but the configured destination cannot accept a required final checkpoint or report after retries
- **THEN** the command exits non-zero and identifies the artifacts that remain local

