# Version matrix

`uv.lock` is the source of truth. The lock resolved on 2026-06-29 with Python 3.12,
Gymnasium 1.3.0, Stable-Baselines3 2.9.0, PyTorch 2.12.1, MuJoCo 3.10.0, JAX 0.10.2,
Brax 0.14.2, Playground 0.2.0, and Pygame 2.6.1. SB3 deliberately does not depend on
JAX, Brax, MJX, or Playground; those packages are confined to the optional MJX extra.

## Nebius L40S benchmark rate

The reproducible benchmark input was recorded from the official Nebius Compute pricing page on
2026-06-29 for the `gpu-l40s-a` `1gpu-8vcpu-32gb` preset. The non-preemptible USD hourly rate is
`1.35 + (8 × 0.012) + (32 × 0.0032) = 1.5484 USD/hour` for GPU, vCPU, and RAM. The run configs store
that explicit rate, currency, and access date; `estimated_cost` is runtime in hours multiplied by
`1.5484`. The rate is a benchmark input rather than a promise of future billing, excludes taxes
and separate storage charges, and should be replaced when another platform, preset, currency, or
pricing date applies. Source: https://docs.nebius.com/compute/resources/pricing

## Nebius cpu-d3 benchmark rate

The showcase SB3 examples train on the `cpu-d3` `8vcpu-32gb` preset, which has no GPU component.
Applying the same published per-resource rates gives `(8 × 0.012) + (32 × 0.0032) = 0.1984
USD/hour`, recorded with access date 2026-07-14. The gallery SB3 run configs store that explicit
rate, currency, and date, and `estimated_cost` is measured runtime in hours multiplied by it.

The custom-robot training profile moved to `16vcpu-64gb` at contract version
`custom-ppo-quick-v2`. The same per-resource rates give `(16 × 0.012) + (64 × 0.0032) = 0.3968
USD/hour`, on the same 2026-07-14 access date; the preparation profile stays on `4vcpu-16gb`.

The same caveats as the L40S rate apply: these are benchmark inputs, not billing promises, and
exclude taxes and storage.
Source: https://docs.nebius.com/compute/resources/pricing

## SB3 Linux/NVIDIA smoke record

Verified on 2026-06-29 on a Linux/NVIDIA GPU validation host. This was a pre-Nebius development
gate only; final challenge acceptance must be rerun on Nebius.

- GPU class: NVIDIA data-center GPU, 23034 MiB
- Host kernel: Ubuntu 24.04 Linux kernel
- NVIDIA driver: `595.71.05`
- Host SB3 health: CUDA available, Torch `2.12.1+cu130`, CUDA runtime reported by Torch `13.0`
- Container base: `nvidia/cuda:12.9.1-runtime-ubuntu24.04`
- Container SB3 health: CUDA available, Torch `2.12.1+cu130`, CUDA runtime reported by Torch `13.0`

Executed gates:

- `uv sync --extra dev --extra sb3`
- `uv run ruff check src tests`
- `uv run mypy src`
- `uv run pytest`
- `uv run python -m sim2policy.health --backend sb3`
- `uv run python -m sim2policy.render --config configs/smoke_sb3.yaml --output runs/gpu-smoke/videos/random.mp4 --smoke-test`
- `uv run python -m sim2policy.train_sb3 --config configs/smoke_sb3.yaml --run-id gpu-smoke`
- `uv run python -m sim2policy.evaluate --config configs/smoke_sb3.yaml --run-id gpu-smoke --checkpoint runs/gpu-smoke/checkpoints/final-000000000256.zip`
- `uv run python -m sim2policy.render --config configs/smoke_sb3.yaml --run-id gpu-smoke --checkpoint runs/gpu-smoke/checkpoints/final-000000000256.zip --output runs/gpu-smoke/videos/final.mp4`
- `docker run --rm --gpus all nvidia/cuda:13.0.2-base-ubuntu24.04 nvidia-smi`
- `docker build --target sb3 --build-arg SOURCE_REVISION=<repo-rev> -t sim2policy:sb3 .`
- `docker run --rm --gpus all sim2policy:sb3 sim2policy.health --backend sb3`
- `docker run --rm --gpus all -v /tmp/sim2policy-container-smoke:/out sim2policy:sb3 sim2policy.render --config configs/smoke_sb3.yaml --output /out/random.mp4 --smoke-test`
- `docker run --rm --entrypoint python sim2policy:sb3 -c '...'` confirmed `jax`,
  `mujoco_playground`, and `brax` are absent from the SB3 image
- `docker run --rm --gpus all -v /tmp/sim2policy-container-train:/work/runs sim2policy:sb3 sim2policy.train_sb3 --config configs/smoke_sb3.yaml --run-id container-smoke --runs-root /work/runs`

Both host and container render smoke selected EGL successfully. OSMesa fallback remains implemented
but was not exercised in this Linux/NVIDIA pass.

## HalfCheetah GPU smoke record

Verified on the same Linux/NVIDIA validation host on 2026-06-29 with `HalfCheetah-v5` and bounded
smoke overrides. This is not a substitute for Nebius acceptance:

- `training.total_steps=4096`
- `training.n_envs=2`
- `training.hyperparameters={n_steps: 128, batch_size: 64, gamma: 0.98, learning_rate: 0.0003, ent_coef: 0.0, clip_range: 0.2}`
- `checkpoint.every_steps=1024`
- `evaluation.episodes=2`
- `rendering.frames=90`
- `rendering.width=320`
- `rendering.height=240`

Executed gates:

- short HalfCheetah training produced initial, step-1024, step-2048, step-3072, step-4096,
  final checkpoint sidecars, metadata, and TensorBoard events
- deterministic evaluation loaded the final checkpoint and wrote `report/metrics.json` plus
  `report/summary.md`
- final checkpoint rollout rendered with EGL to `videos/final.mp4`
- progression montage rendered initial, nearest-quarter, and final videos plus
  `videos/progression.mp4`

SB3 selected CUDA on the host and emitted the expected warning that MLP PPO may underutilize GPU;
this is recorded as an honest baseline characteristic, not a failure.

## S3 sync/resume smoke record

Verified against a disposable S3-compatible test bucket on 2026-06-29:

1. Ran `halfcheetah-s3-smoke` to 1024 steps with `storage.mode=s3`, `checkpoint.every_steps=512`.
2. Confirmed remote checkpoint objects and `checkpoints/latest.json` existed under the configured
   `s3://<bucket>/sim2policy/halfcheetah-s3-smoke/` prefix.
3. Deleted the local run directory.
4. Ran the same run ID with `--resume remote` and `training.total_steps=2048`.
5. Confirmed local training resumed from the downloaded 1024-step checkpoint and published
   1536-step, 2048-step, and final-2048 artifacts.
6. Confirmed remote `checkpoints/latest.json` referenced `final-000000002048.zip`.

## Ant GPU smoke record

Verified on the same Linux/NVIDIA validation host on 2026-06-29 with `Ant-v5` and bounded smoke
overrides:

- `training.total_steps=1024`
- `training.n_envs=2`
- `training.hyperparameters={n_steps: 128, batch_size: 64, gamma: 0.98, learning_rate: 0.0003, ent_coef: 0.0, clip_range: 0.2}`
- `checkpoint.every_steps=512`

The run produced metadata, TensorBoard events, initial checkpoint, periodic step-512 and step-1024
checkpoints, final-1024 checkpoint, and all checkpoint sidecars. Convergence was not expected or
claimed for this bounded artifact-contract smoke.

## SB3 callback composition smoke record

Verified on the same Linux/NVIDIA validation host on 2026-06-29 with the lightweight
`smoke_sb3.yaml` run
`eval-callback-smoke`. The composed callback produced durable periodic checkpoints, final
checkpoint, TensorBoard eval scalars, `report/eval/evaluations.npz`, and
`checkpoints/best/best_model.zip`.

## Telemetry smoke record

Verified on the same Linux/NVIDIA validation host on 2026-06-29 with the lightweight `telemetry-smoke`
run. Training wrote `report/runtime.json` with wall-clock timestamps and best-effort GPU snapshots;
evaluation wrote `report/metrics.json` with wall-clock timestamps, GPU snapshot metadata, and
`benchmark.gpu_utilization_percent`. GPU utilization may be `0.0` for CPU-configured smoke runs
and telemetry unavailability is represented as structured metadata rather than a workflow failure.

## MJX Linux/NVIDIA smoke record

Verified on the same Linux/NVIDIA validation host on 2026-06-29. This is not a substitute for the
final Nebius Track A run, but it validates the local pinned stack and adapter contract:

- Python 3.12
- NumPy 2.2.6
- JAX/JAXlib 0.6.2 with CUDA 12 plugin
- MuJoCo/MuJoCo MJX 3.10.0
- Brax 0.14.2
- Playground 0.2.0
- Selected environment: `Go1JoystickFlatTerrain`
- Required Playground implementation override: `impl=jax`

Why the pins/override matter:

- NumPy 2.5.0 broke `mediapy` import in `train-jax-ppo`; NumPy is capped below 2.3.
- JAX 0.10.2 removed `jax.device_put_replicated`, which Brax 0.14.2 still calls; JAX is capped
  below 0.7.
- The Playground Go1 default config used `impl=warp`, which failed in this wheel set during MJX
  model conversion; the Sim2Policy MJX config and adapter explicitly force `impl=jax`.

Executed gates:

- `uv sync --extra dev --extra mjx`
- `uv run python -m sim2policy.health --backend mjx` reported JAX backend `gpu`
- raw Playground smoke:
  `train-jax-ppo --env_name=Go1JoystickFlatTerrain --impl=jax --num_timesteps=1024 ...`
- Sim2Policy adapter smoke:
  `uv run python -m sim2policy.train_mjx --config configs/go1_mjx.yaml --run-id mjx-adapter-smoke ...`
- MJX image build:
  `docker build --target mjx --build-arg SOURCE_REVISION=<repo-rev> -t sim2policy:mjx .`
- MJX image smoke:
  `docker run --rm --gpus all sim2policy:mjx sim2policy.health --backend mjx`
- MJX image environment smoke loaded `Go1JoystickFlatTerrain` with `impl=jax`, observation sizes
  `state=(48,)`, `privileged_state=(123,)`, and action size `12`

The adapter smoke produced:

- `runs/mjx-adapter-smoke/checkpoints/final-000000001280.zip`
- `runs/mjx-adapter-smoke/checkpoints/final-000000001280.zip.json`
- raw Playground Orbax checkpoint/log output under `runs/mjx-adapter-smoke/mjx_logs/`
- `runs/mjx-adapter-smoke/report/runtime.json`

The image includes `git` because MuJoCo Playground downloads MuJoCo Menagerie on first quadruped
environment load.

The adapter now creates a true step-zero Brax policy in an isolated process, derives periodic save
cadence from the common checkpoint config, restores published zipped Orbax checkpoints through
`brax.training.agents.ppo.checkpoint.load_policy`, performs deterministic multi-seed locomotion
evaluation, and renders Playground trajectories through the common media command. The new adapter
paths are unit-tested; final Nebius GPU acceptance is recorded separately once the pushed image
passes its bounded cloud gate.

## Nebius Serverless AI GPU visibility record

The official `nvidia-smi` quickstart completed on 2026-06-29 as Nebius job
`aijob-e00sescyvnw0qat56h` using CLI 0.12.216, platform `gpu-l40s-a`, preset
`1gpu-8vcpu-32gb`, and a one-hour safety timeout. It reported NVIDIA L40S with 46,068 MiB,
driver 580.159.04, and CUDA 13.1. The workload started at `20:30:07.012590730Z` and finished at
`20:30:07.391463500Z`.
