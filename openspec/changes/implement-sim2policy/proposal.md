## Why

Training and demonstrating a robot locomotion policy currently requires users to assemble reinforcement-learning code, GPU/container dependencies, ephemeral-job persistence, evaluation, and headless rendering themselves. Sim2Policy will provide a reproducible Nebius Serverless AI template that turns a configuration and one job submission into durable checkpoints, metrics, and a visible progression from an untrained policy to a walking robot.

## What Changes

- Add two configurable PPO training backends: a dependable Gymnasium MuJoCo + Stable-Baselines3 path and a GPU-native MuJoCo MJX + Brax/MuJoCo Playground path.
- Add durable run storage with periodic checkpoint, TensorBoard, report, and video uploads to S3-compatible object storage, including resume-from-latest-checkpoint behavior.
- Add deterministic rollout rendering for untrained, intermediate, and final policies, with EGL-to-OSMesa fallback and progression montage generation.
- Add repeatable multi-seed evaluation, success-threshold tracking, reward curves, runtime/GPU/cost metrics, and backend comparison reports.
- Add a CUDA-enabled container, environment configs, Nebius Serverless AI job submission wrapper, Make targets, smoke tests, and a clone-and-run tutorial.
- Deliver Track B first as the end-to-end baseline, then integrate Track A behind the same run/artifact conventions without making Track B depend on it.

## Capabilities

### New Capabilities
- `policy-training-backends`: Configurable SB3 and MJX PPO training, checkpoint production, backend selection, and supported locomotion environments.
- `durable-run-artifacts`: Portable S3-compatible artifact layout, periodic synchronization, final upload, and checkpoint-based resumption for ephemeral jobs.
- `rollout-media`: Headless deterministic rollout rendering, rendering fallback, checkpoint progression videos, and montage output.
- `policy-evaluation-reporting`: Multi-seed policy evaluation, success criteria, machine-readable metrics, reward curves, and backend cost/performance comparison.
- `serverless-template-workflow`: Reproducible container builds, local/cloud smoke paths, Nebius job submission, Make targets, configuration, and operator documentation.

### Modified Capabilities

None.

## Impact

- Adds the `sim2policy/` template project, including Python training/render/evaluation/storage modules, YAML configs, container definition, job scripts, Make targets, tests, documentation, and sample assets.
- Introduces Python, MuJoCo, Stable-Baselines3/PyTorch, JAX/MJX, MuJoCo Playground/Brax, boto3, TensorBoard, image/video, and YAML dependencies with pinned GPU-compatible versions.
- Integrates with a container registry, Nebius Serverless AI Jobs, an S3-compatible object-storage endpoint, and optional GPU telemetry/cost inputs.
- Produces potentially large checkpoints, logs, reports, and videos under a stable per-run object-storage prefix rather than committing generated run data to the repository.
