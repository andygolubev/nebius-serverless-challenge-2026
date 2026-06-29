# Version matrix

`uv.lock` is the source of truth. The lock resolved on 2026-06-29 with Python 3.12,
Gymnasium 1.3.0, Stable-Baselines3 2.9.0, PyTorch 2.12.1, MuJoCo 3.10.0, JAX 0.10.2,
Brax 0.14.2, Playground 0.2.0, and Pygame 2.6.1. SB3 deliberately does not depend on
JAX, Brax, MJX, or Playground; those packages are confined to the optional MJX extra.

## SB3 Linux/NVIDIA smoke record

Verified on 2026-06-29 in AWS `eu-west-2` with the single-stack debug environment in
`infra/aws-debug-g6.yaml`.

- Instance: `g6.2xlarge`
- GPU: NVIDIA L4, 23034 MiB
- Host AMI parameter:
  `/aws/service/deeplearning/ami/x86_64/oss-nvidia-driver-gpu-pytorch-2.12-ubuntu-24.04/latest/ami-id`
- Host kernel: Ubuntu 24.04 AWS kernel `6.17.0-1019-aws`
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
- `uv run python -m sim2policy.render --config configs/smoke_sb3.yaml --output runs/aws-smoke/videos/random.mp4 --smoke-test`
- `uv run python -m sim2policy.train_sb3 --config configs/smoke_sb3.yaml --run-id aws-smoke`
- `uv run python -m sim2policy.evaluate --config configs/smoke_sb3.yaml --run-id aws-smoke --checkpoint runs/aws-smoke/checkpoints/final-000000000256.zip`
- `uv run python -m sim2policy.render --config configs/smoke_sb3.yaml --run-id aws-smoke --checkpoint runs/aws-smoke/checkpoints/final-000000000256.zip --output runs/aws-smoke/videos/final.mp4`
- `docker run --rm --gpus all nvidia/cuda:13.0.2-base-ubuntu24.04 nvidia-smi`
- `docker build --target sb3 --build-arg SOURCE_REVISION=<repo-rev> -t sim2policy:sb3 .`
- `docker run --rm --gpus all sim2policy:sb3 sim2policy.health --backend sb3`
- `docker run --rm --gpus all -v /tmp/sim2policy-container-smoke:/out sim2policy:sb3 sim2policy.render --config configs/smoke_sb3.yaml --output /out/random.mp4 --smoke-test`
- `docker run --rm --entrypoint python sim2policy:sb3 -c '...'` confirmed `jax`,
  `mujoco_playground`, and `brax` are absent from the SB3 image
- `docker run --rm --gpus all -v /tmp/sim2policy-container-train:/work/runs sim2policy:sb3 sim2policy.train_sb3 --config configs/smoke_sb3.yaml --run-id container-smoke --runs-root /work/runs`

Both host and container render smoke selected EGL successfully. OSMesa fallback remains implemented
but was not exercised in this AWS pass.

## MJX status

The MJX dependency matrix remains a candidate until a Linux/GPU smoke gate validates JAX accelerator
discovery and a selected MuJoCo Playground environment step/training path. Do not present Track A as
tested until that gate passes.
