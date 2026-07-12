# serverless-template-workflow Specification

## Purpose
Make the template clone-and-run: reproducible SB3/MJX container targets, a progressive
cheap-to-expensive smoke workflow, a validated no-shell-evaluation Nebius job submission wrapper
(`jobs/submit.sh`) with dry-run support, unified Make targets, tutorial-grade documentation, and
lightweight sample deliverables without large artifacts in Git.

## Requirements
### Requirement: Reproducible backend images
The system SHALL provide CUDA-capable container build targets for SB3 and MJX with tested dependency pins, MuJoCo headless libraries, ffmpeg, unbuffered logs, and no embedded credentials.

#### Scenario: SB3 image is built
- **WHEN** an operator builds the SB3 target from a clean checkout
- **THEN** the image installs the locked SB3 dependency set and can run CUDA visibility, training import, and rendering smoke checks without MJX packages

#### Scenario: MJX image is built
- **WHEN** an operator builds the MJX target
- **THEN** the image installs the recorded compatible CUDA/JAX/MJX/Playground set and can run its accelerator and environment smoke checks

### Requirement: Progressive smoke workflow
The project SHALL document and expose checks for local unit/import/render behavior, container GPU visibility, registry pull and CUDA visibility in Nebius, short training with storage sync, and full training in that order.

#### Scenario: Operator follows cloud preflight
- **WHEN** an operator prepares a first full training run
- **THEN** the documented workflow makes each lower-cost smoke gate independently runnable before the full job

### Requirement: Safe Nebius job submission
The submission wrapper SHALL accept image, config/environment, run ID, platform, preset, timeout, subnet, and storage inputs, SHALL validate required values, SHALL construct arguments without shell evaluation of user-provided values, and SHALL support a no-submit dry run.

#### Scenario: Valid job is submitted
- **WHEN** all required values are supplied and dry run is disabled
- **THEN** the wrapper invokes the documented Nebius CLI job command with the selected training module and spending timeout

#### Scenario: Submission is previewed
- **WHEN** dry run is enabled
- **THEN** the wrapper prints a safely escaped command with secrets redacted and does not create a cloud job

#### Scenario: Required parameter is absent
- **WHEN** a required cloud or run parameter is missing
- **THEN** the wrapper exits before invoking Nebius and identifies the missing parameter

### Requirement: Unified developer commands
The project SHALL provide Make targets for environment setup, tests, backend image builds, image push, smoke checks, training, rendering, evaluation, reporting, and cleanup, with environment/config and run ID passed explicitly.

#### Scenario: User starts a configured run
- **WHEN** a user invokes the documented training target with an environment and run ID
- **THEN** Make delegates to the corresponding validated local or cloud workflow without requiring source edits

### Requirement: Clone-and-run tutorial
The repository SHALL document prerequisites, architecture, a short quickstart, configuration fields, cloud resources, secret handling, cost controls, artifact layout, resumption, adding an environment, and troubleshooting for EGL, OSMesa, JAX/CUDA, quota, subnet, registry, and storage errors.

#### Scenario: New user follows the quickstart
- **WHEN** a user with the documented prerequisites follows the README from a clean clone
- **THEN** the user can run tests and smoke checks, build the appropriate image, preview a job, submit it, and locate its durable outputs without undocumented steps

### Requirement: Lightweight sample deliverables
The repository SHALL include or link lightweight representative reward curves and teaser media while excluding large generated checkpoints, logs, and full videos from version control.

#### Scenario: Repository contents are inspected
- **WHEN** a user clones the template
- **THEN** sample visuals are available for understanding the result and ignore rules prevent accidental addition of large run artifacts or secrets

