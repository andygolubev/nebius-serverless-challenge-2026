## Context

The repository currently contains the challenge shell and a detailed implementation plan, but no training application. The deliverable must combine reinforcement-learning code, GPU/runtime dependencies, durable artifacts from ephemeral jobs, headless media generation, evaluation, cloud submission, and approachable documentation.

The implementation has two deliberately unequal tracks. Track B (Gymnasium MuJoCo + Stable-Baselines3 PPO) is the dependable end-to-end baseline and must ship first. Track A (MuJoCo MJX + MuJoCo Playground/Brax PPO) adds the GPU-native simulation story after the shared pipeline is proven. A failure or incompatibility in Track A must not prevent users from running Track B.

Primary users are hackathon evaluators and developers cloning the repository. Operators provide registry, Nebius, and S3-compatible storage settings through environment variables and command parameters; no cloud credentials belong in source control. Serverless jobs are ephemeral, so the object-store run prefix is the durable system of record for valuable outputs.

## Goals / Non-Goals

**Goals:**

- Provide a cloneable, configuration-driven path from local smoke test to a trained locomotion policy in a Nebius Serverless AI Job.
- Produce reproducible checkpoints, logs, evaluations, reports, and rollout media under one run identity.
- Make Track B independently complete, then expose Track A through the same configuration, storage, render, and report conventions where backend formats allow.
- Detect dependency, rendering, storage, and cloud wiring problems with short smoke commands before expensive training runs.
- Give a new user enough operational guidance to reproduce the demo and add a compatible environment.

**Non-Goals:**

- Inventing a PPO implementation or tuning hyperparameters from scratch.
- Building a hosted dashboard, job scheduler, or object-storage service.
- Guaranteeing convergence for arbitrary environments or user-supplied reward functions.
- Committing large generated checkpoints, raw TensorBoard logs, or full videos to Git.
- Requiring Humanoid training on the CPU-simulation backend.

## Decisions

### 1. Use a phased, backend-adapter architecture

The application will expose backend-specific trainers (`train_sb3.py` and `train_mjx.py`) behind common run configuration and artifact conventions. Shared modules will own validated configuration, run metadata, object-storage operations, evaluation/report schemas, and command-line behavior. Track B is implemented and accepted first; Track A is an additive phase with a documented cutoff if JAX/CUDA integration cannot be stabilized.

This is preferred over a single polymorphic trainer because SB3 and Brax/Playground have materially different checkpoint, vectorization, callback, and inference APIs. It is preferred over separate projects because shared run identity and output conventions are central to the template and comparison demo.

### 2. Treat YAML configuration plus CLI overrides as the run contract

Each environment config will declare backend, environment identifier, seed, training budget, parallelism, checkpoint cadence, evaluation settings, success threshold, and backend-specific hyperparameters. CLI flags will select the config and supply run identity or narrowly scoped overrides. Startup validation will reject missing, incompatible, or unknown critical settings before creating an expensive job.

Resolved configuration, package versions, source revision when available, start time, backend, environment, and device information will be written to run metadata. Tuned SB3 values will be adapted from RL Baselines3 Zoo and recorded in-repo; Playground defaults will be selected explicitly rather than silently following whatever a newly installed package version provides.

### 3. Make the local run directory canonical during execution and S3 canonical across jobs

Every process writes first to `runs/<run_id>/` using fixed subdirectories: `checkpoints/`, `tensorboard/`, `videos/`, and `report/`. `storage.py` maps these paths to `s3://<bucket>/<prefix>/<run_id>/...` through an endpoint-configurable boto3 client. Local-only mode remains supported when storage is not configured.

Checkpoint publication uses a completed-file upload followed by a small latest-checkpoint manifest, so resume does not select a partial object. Periodic sync is driven by trainer callbacks/timers, while a best-effort shutdown handler and mandatory normal-completion sync publish remaining artifacts. At startup, an explicit resume mode downloads the newest compatible checkpoint and restores the training step; incompatibility fails before training.

Explicit S3 synchronization is preferred over a mounted bucket because it is portable across S3-compatible providers and makes lifecycle/error behavior testable. Mounting can be documented later as an operator alternative, not required behavior.

### 4. Decouple rendering and evaluation from training

Training jobs will save an initial policy snapshot, periodic checkpoints, and a final checkpoint. Separate commands consume a checkpoint and resolved run metadata to render or evaluate it. This keeps graphics failures from invalidating training and lets media/evaluation run on a different machine.

The render command will run deterministic inference with a fixed default seed, preserve frames across episode resets, and encode MP4 through imageio/ffmpeg. Rendering starts with EGL and retries the render process once with OSMesa when graphics initialization fails. The retry occurs in a fresh process because MuJoCo graphics backend selection is process-global. A montage command selects initial, approximately 25%-progress, and final checkpoints and labels/stitches their videos with ffmpeg.

### 5. Use a stable evaluation/report schema

Evaluation defaults to 20 deterministic episodes distributed across five seeds. It records per-episode reward/length and aggregate mean, standard deviation, success count/rate, threshold, checkpoint identity, backend, environment, and evaluation seeds in `report/metrics.json`. A Markdown summary adds reward-curve assets and, when resource/rate data is supplied, wall-clock-to-threshold, GPU utilization, and estimated cost.

Backend comparisons consume individual metrics documents rather than parsing console output. Missing optional utilization or price information is represented as unavailable, never fabricated. Success thresholds are environment configuration, allowing HalfCheetah and Ant reward thresholds and locomotion-specific MJX criteria to use one report schema.

### 6. Build one reproducible operator surface with optional backend dependency groups

The Python project will define base/shared, SB3, and MJX dependency groups with tested pins. The container definition will provide named build targets (or equivalent build arguments) so the dependable SB3 image does not install JAX/Playground, while an MJX image pins the tested CUDA/JAX combination. Both images include the libraries and ffmpeg needed by headless rendering. CI/local checks will cover CPU-compatible unit tests; GPU and Nebius smoke commands are explicit acceptance gates.

`jobs/submit.sh` will validate required parameters, construct an argument array without evaluating user input, and expose image, environment/config, run ID, platform/preset, timeout, subnet, and storage settings. The Makefile is the human-facing command index for setup, test, build, smoke, train, render, evaluate, report, and image push. Current Nebius CLI flags and image/platform identifiers will be verified against official documentation during implementation and kept centralized in the wrapper.

### 7. Keep secrets and spend controls outside artifacts

Credentials are accepted only through the job environment/secret mechanism or the user's local environment and are excluded from metadata and logs. Run IDs and object keys are validated to prevent path/prefix traversal. Debug job examples use short timeouts, and full jobs require an explicit timeout; documentation includes quota, GPU visibility, registry pull, storage sync, and JAX/CUDA preflight steps.

## Risks / Trade-offs

- **JAX, CUDA, MJX, and Playground versions are incompatible** → Pin and smoke-test a known combination in the MJX image; keep dependency groups/images isolated; enforce the end-of-phase cutoff without weakening Track B.
- **EGL is unavailable or misconfigured in the job image** → Render out of process, retry with OSMesa, and keep rendering separate from training.
- **A timeout interrupts checkpoint upload** → Save on a bounded cadence, publish checkpoints before updating the latest manifest, sync incrementally, and resume only compatible completed checkpoints.
- **SB3 underutilizes the GPU** → Present it as the reliability baseline, record honest utilization, and reserve GPU-simulation performance claims for MJX.
- **Policies do not reach the success threshold** → Start from recorded tuned/default configs, run short validation jobs before full budgets, and report actual outcomes rather than hiding failed seeds.
- **One image becomes too large or dependency resolution becomes brittle** → Use backend-specific dependency groups/build targets while preserving one source tree and command contract.
- **Cloud CLI syntax changes** → Centralize CLI assembly, document the verified CLI version, and cover submission generation with a dry-run test.
- **Periodic storage failures interrupt useful training** → Retry transient sync operations with bounded backoff, retain local artifacts, surface degraded sync status, and fail the final job if required durable outputs cannot be published.
- **Benchmark comparisons become misleading** → Record device, versions, budgets, seeds, and threshold definitions; only compare like-for-like criteria and label unavailable values.

## Migration Plan

1. Establish the project skeleton, configuration schema, shared run metadata, and tests without cloud dependencies.
2. Complete Track B local training, checkpoint, deterministic evaluation, and ten-frame render smoke flow.
3. Add containerized headless rendering and SB3 dependency pins; pass CUDA visibility and EGL/OSMesa smoke gates.
4. Add S3-compatible sync/resume and verify interruption recovery before submitting a full cloud run.
5. Add the Nebius wrapper, Make targets, dry-run coverage, and progressively run official GPU, image, storage, short-training, and full-training cloud gates.
6. Add Track A in its isolated image/dependency group and reuse the common run/report conventions; stop Track A work at the planned cutoff if its gate fails.
7. Produce evaluation reports, progression media, sample lightweight assets, and the clone-and-run tutorial.

Rollback is additive: retain the last passing Track B image/config and disable or omit MJX targets if Track A fails. Object-store outputs are versioned by run ID, so failed experiments do not overwrite a known-good run.

## Open Questions

- Which exact Nebius GPU platform/preset names and CLI flags are current at implementation time? Resolve against official docs before the submission wrapper is accepted.
- Which mutually compatible CUDA, JAX, MuJoCo, Brax, and MuJoCo Playground versions pass the target GPU smoke test? Record the tested matrix in the lockfile and README.
- What on-demand GPU rate source will be used for the final cost calculation? Store the rate and currency as explicit report inputs with an access date.
- Which MuJoCo Playground locomotion environment offers the most reliable quadruped demo on the available GPU? Select it after the MJX smoke gate; keep the config name stable once sample artifacts are published.
