## 1. Project Foundation

- [x] 1.1 Create the `sim2policy` package layout, `src` package, configs, jobs, tests, assets, runs placeholder, and module entry points described by the design
- [x] 1.2 Define `pyproject.toml` metadata, Python version, CLI entry points, formatting/lint/test tooling, and isolated shared, SB3, and MJX dependency groups
- [x] 1.3 Add a lockfile and document the initially tested Python, CUDA, MuJoCo, PyTorch, and SB3 versions without adding MJX dependencies to the SB3 group
- [x] 1.4 Add ignore rules for credentials, local environment files, runs, checkpoints, TensorBoard logs, and large generated media while retaining lightweight sample assets
- [x] 1.5 Configure unit tests and static checks and prove the shared package imports in a base-only environment

## 2. Configuration and Run Lifecycle

- [x] 2.1 Implement typed YAML configuration models for backend, environment, training, checkpoint, evaluation, success, rendering, storage, and reporting settings
- [x] 2.2 Implement deterministic CLI override resolution and fail-fast validation for unknown, missing, unsafe, and backend-incompatible values
- [x] 2.3 Implement safe run-ID validation and the canonical local `checkpoints`, `tensorboard`, `videos`, and `report` directory creation
- [x] 2.4 Implement redacted run metadata capture for resolved config, seed, versions, source revision, device, backend, environment, and timestamps
- [x] 2.5 Add representative valid and invalid configuration fixtures and unit tests for resolution, redaction, compatibility checks, and run-path traversal rejection
- [x] 2.6 Add recorded HalfCheetah and Ant SB3 configs using cited RL Baselines3 Zoo-derived PPO values and short smoke-test overrides

## 3. Track B Training Baseline

- [x] 3.1 Implement the SB3 trainer CLI with seeded vectorized Gymnasium MuJoCo environments, resolved hyperparameters, device selection, and TensorBoard logging
- [x] 3.2 Implement initial, periodic, and final SB3 checkpoint creation with step and compatibility metadata
- [x] 3.3 Implement SB3 callback composition for checkpoint cadence, evaluation logging, sync hooks, graceful interruption, and finalization
- [x] 3.4 Implement compatible local SB3 checkpoint resume while preserving the cumulative timestep and checkpoint numbering
- [x] 3.5 Add unit tests with lightweight fake environments for trainer setup, callback cadence, initial/final snapshots, interruption, and resume compatibility
- [x] 3.6 Run a short local HalfCheetah training session and verify metadata, TensorBoard events, periodic checkpoints, and a loadable final policy
- [x] 3.7 Run the Ant smoke configuration and verify the same artifact contract without requiring convergence

## 4. Deterministic Evaluation and Reports

- [x] 4.1 Define and document the versioned `metrics.json` schema for run identity, checkpoint, per-episode data, aggregates, success, runtime, device, and versions
- [x] 4.2 Implement SB3 deterministic evaluation with configurable episodes/seeds and the default 20-episode, five-seed distribution
- [x] 4.3 Implement configurable mean-reward and locomotion-condition success evaluators without coupling report generation to one backend's reward semantics
- [x] 4.4 Implement reward-log parsing, threshold-crossing detection, and reward-curve PNG generation from TensorBoard data
- [x] 4.5 Implement Markdown report generation with explicit unavailable states for missing utilization or price inputs
- [x] 4.6 Add tests for deterministic seed scheduling, aggregate statistics, success/no-success reports, schema validation, threshold crossing, and unavailable benchmark values
- [x] 4.7 Evaluate the local HalfCheetah smoke checkpoint and verify both machine-readable and human-readable report outputs

## 5. Rollout Rendering and Progression Media

- [x] 5.1 Implement backend-aware checkpoint validation and deterministic SB3 RGB rollout rendering across termination and truncation boundaries
- [x] 5.2 Implement MP4 encoding with configurable frame count, frame rate, dimensions, output metadata, and validation of the encoded result
- [x] 5.3 Implement EGL rendering orchestration with a single fresh-process OSMesa retry and clear reporting of the successful graphics backend
- [x] 5.4 Implement a random-policy render smoke command that validates at least ten frames without a trained checkpoint
- [x] 5.5 Implement initial/nearest-quarter/final checkpoint selection and labeled ffmpeg progression montage generation while retaining source videos
- [x] 5.6 Add tests for episode resets, checkpoint mismatch, quarter-checkpoint selection, EGL failure handoff, and ffmpeg command construction
- [x] 5.7 Render the local HalfCheetah smoke checkpoint and verify a playable MP4 plus progression montage using available snapshots

## 6. Durable S3-Compatible Artifacts

- [x] 6.1 Implement endpoint-configurable boto3 client construction using the standard credential chain and an explicit local-only mode
- [x] 6.2 Implement safe local-to-remote run path mapping and incremental synchronization for checkpoints, TensorBoard logs, videos, and reports
- [x] 6.3 Implement bounded retry/backoff, degraded-sync state recording, secret-safe diagnostics, and non-zero finalization when required final uploads fail
- [x] 6.4 Implement completed-checkpoint upload followed by atomic latest-manifest publication with backend, environment, step, checksum, and compatibility metadata
- [x] 6.5 Implement explicit remote resume discovery, manifest/checksum validation, checkpoint download, and incompatibility rejection
- [x] 6.6 Wire periodic and final synchronization into SB3 callbacks and wire report/video commands to publish their outputs
- [x] 6.7 Add mocked S3 tests for layout, local-only behavior, partial upload, retry exhaustion, manifest ordering, redaction, and compatible/incompatible resume
- [x] 6.8 Exercise upload, interruption, latest-checkpoint selection, and resume against a disposable S3-compatible test bucket or emulator

## 7. Reproducible Containers and Local Gates

- [x] 7.1 Implement CUDA-based SB3 and MJX container build targets with shared MuJoCo headless libraries, ffmpeg, unbuffered logs, and backend-specific locked installs
- [x] 7.2 Add container health/smoke commands for package imports, CUDA visibility, MuJoCo environment creation, and EGL-to-OSMesa frame rendering
- [x] 7.3 Verify the SB3 image contains no MJX/JAX dependency and passes unit, import, random-render, and short-training smoke checks
- [x] 7.4 Verify the SB3 image on an NVIDIA runtime can see the GPU and produce a headless MP4, recording OSMesa-only fallback if EGL is unavailable locally
- [x] 7.5 Add image labels or generated version output that captures source revision and locked dependency versions without embedding secrets

## 8. Nebius Submission and Operator Commands

- [ ] 8.1 Verify current Nebius Serverless AI Job CLI syntax, authentication, secret/environment support, GPU platform/preset identifiers, subnet requirements, and timeout behavior against official documentation
- [x] 8.2 Implement `jobs/submit.sh` with required-value validation, argument-array construction, backend module selection, mandatory timeout, and no shell evaluation of inputs
- [x] 8.3 Implement redacted dry-run output and tests for command construction, whitespace/special-character handling, missing parameters, backend selection, and secret suppression
- [x] 8.4 Implement Make targets for setup, checks, tests, backend builds, push, local smoke/train, cloud dry-run/train, render, evaluate, report, and cleanup
- [x] 8.5 Write the jobs reference for account/quota prerequisites, registry, subnet, storage/secret injection, short-debug timeouts, status/log inspection, cancellation, and artifact retrieval

## 9. Track B Cloud Acceptance

- [ ] 9.1 Run the official Nebius GPU visibility quickstart and record the verified CLI version, GPU platform/preset, and non-secret command settings
- [ ] 9.2 Push the SB3 image and run a minimal job that verifies registry pull, package imports, CUDA visibility, and headless rendering
- [ ] 9.3 Run a bounded ten-minute HalfCheetah job and verify checkpoints and TensorBoard files appear incrementally in object storage
- [ ] 9.4 Interrupt or time-limit a smoke run, resume it from the remote latest checkpoint, and verify cumulative progress and artifact continuity
- [ ] 9.5 Run the full HalfCheetah configuration, evaluate the final checkpoint, render initial/mid/final rollouts, and publish the run report
- [ ] 9.6 Run the bounded Ant configuration through training, evaluation, rendering, and durable publication; record actual success or failure without altering results

## 10. Track A GPU-Native Training

- [ ] 10.1 Select a reliable MuJoCo Playground quadruped environment and record the chosen environment/config API instead of depending on an implicit package default
- [ ] 10.2 Establish and lock a CUDA/JAX/MuJoCo/MJX/Brax/Playground version matrix that passes accelerator discovery and environment-step smoke tests in the MJX image
- [x] 10.3 Add the Go1-or-selected-quadruped YAML configuration with parallelism, training budget, checkpoint cadence, evaluation seeds, and sustained-locomotion success criterion
- [ ] 10.4 Implement the MJX trainer adapter with seeded Playground/Brax PPO configuration, initial/periodic/final checkpointing, metadata, and actionable optional-dependency errors
- [ ] 10.5 Implement MJX checkpoint loading adapters for deterministic evaluation and rollout rendering under the common metrics and media contracts
- [ ] 10.6 Wire MJX periodic/final S3 sync and compatible checkpoint resume or explicitly document and test any library-imposed resume limitation before cloud training
- [ ] 10.7 Add tests for MJX config mapping, missing dependencies, checkpoint metadata, success evaluation, and backend isolation from SB3
- [ ] 10.8 Run the MJX image smoke gate locally or on Nebius and stop Track A work at the documented cutoff if the pinned stack cannot pass it, preserving the complete Track B deliverable
- [ ] 10.9 Run a bounded and then full quadruped cloud job, evaluate it, render progression media, and publish durable artifacts if the smoke gate passes

## 11. Benchmarking and Comparison

- [x] 11.1 Capture wall-clock timestamps and GPU telemetry for comparable Track A and Track B runs without blocking training when telemetry is unavailable
- [ ] 11.2 Obtain an explicit dated Nebius rate and currency input and implement reproducible runtime-times-rate cost calculation
- [x] 11.3 Implement comparison-table generation from versioned metrics documents with compatibility/context disclosures and unavailable-value handling
- [x] 11.4 Add tests for cost arithmetic, rate metadata, mismatched comparison context, partial telemetry, and honest unavailable fields
- [x] 11.5 Generate the final Track A versus Track B comparison when both runs exist, or generate a Track B-only benchmark that clearly marks Track A as not completed

## 12. Tutorial, Demo Assets, and Release Verification

- [x] 12.1 Replace the root README with the Sim2Policy tutorial covering RL vocabulary, architecture, 15-minute quickstart, configs, environment extension, artifacts, resume, costs, and troubleshooting
- [x] 12.2 Add a concise architecture diagram and document the phased Track B-first workflow, MJX cutoff, smoke-gate sequence, and expected local/cloud outputs
- [x] 12.3 Add sanitized sample configs, metrics, reward curves, and a lightweight teaser GIF or linked full videos without committing large checkpoints, logs, or secrets
- [x] 12.4 Document and rehearse the 60–90 second demo recording and three-minute judge narrative using actual commands and measured outputs
- [x] 12.5 Run all automated checks from a clean environment and execute every documented local quickstart command exactly as written
- [x] 12.6 Perform a secret and large-file audit, validate all links and example commands, and verify clone-to-dry-run behavior from a clean checkout
- [ ] 12.7 Complete the submission checklist with repository, image reference, checkpoint links, rollout videos, logs, benchmark report, demo recording, and reproducibility writeup
