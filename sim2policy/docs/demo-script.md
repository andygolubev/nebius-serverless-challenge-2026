# Demo script

## 60–90 second recording

1. Open with the one-line promise: “Sim2Policy turns a YAML locomotion config into durable policy
   checkpoints, evaluation metrics, and rollout media from a disposable GPU job.”
2. Show the config:
   `configs/halfcheetah_sb3.yaml`
3. Show the smoke command:
   `uv run python -m sim2policy.train_sb3 --config configs/halfcheetah_sb3.yaml --run-id demo --set training.total_steps=4096 --set training.n_envs=2 --set checkpoint.every_steps=1024`
4. Show the artifact tree:
   `runs/demo/{metadata.json,checkpoints,tensorboard,videos,report}`
5. Show `report/metrics.json` and `report/summary.md`.
6. Play or show the progression montage: initial, nearest-quarter, final.
7. End with the reliability point: checkpoints publish before `latest.json`, so interrupted jobs can
   resume only from completed compatible checkpoints.

## Three-minute judge narrative

- Problem: RL demos usually fail at the boring seams: dependency pinning, headless rendering,
  ephemeral jobs, object storage, resumption, and honest reporting.
- Track B: Stable-Baselines3 + Gymnasium MuJoCo is the dependable baseline. It produces initial,
  periodic, final, and best checkpoints, TensorBoard logs, metrics, reports, and videos.
- Durability: every run has a validated run ID and a fixed artifact layout. S3-compatible storage is
  endpoint-configurable and uses the standard credential chain.
- Evaluation: deterministic multi-seed evaluation writes machine-readable metrics and a Markdown
  report. Optional utilization and cost values stay unavailable unless measured inputs exist.
- Rendering: rollout rendering is deterministic, handles episode boundaries, and retries EGL
  failures once in a fresh OSMesa process.
- Track A: MJX/JAX is isolated behind its own dependency group and smoke gate so it can never break
  the Track B deliverable.

## Commands rehearsed on a Linux/NVIDIA validation host

```bash
uv sync --extra dev --extra sb3
uv run ruff check src tests
uv run mypy src
uv run pytest
uv run python -m sim2policy.health --backend sb3
uv run python -m sim2policy.train_sb3 --config configs/halfcheetah_sb3.yaml --run-id halfcheetah-gpu-smoke --set training.total_steps=4096 --set training.n_envs=2 --set checkpoint.every_steps=1024
uv run python -m sim2policy.evaluate --config configs/halfcheetah_sb3.yaml --run-id halfcheetah-gpu-smoke --checkpoint runs/halfcheetah-gpu-smoke/checkpoints/final-000000004096.zip --set training.total_steps=4096 --set training.n_envs=2 --set checkpoint.every_steps=1024 --set evaluation.episodes=2
uv run python -m sim2policy.render --config configs/halfcheetah_sb3.yaml --run-id halfcheetah-gpu-smoke --checkpoint runs/halfcheetah-gpu-smoke/checkpoints/final-000000004096.zip --output runs/halfcheetah-gpu-smoke/videos/final.mp4 --set rendering.frames=90 --set rendering.width=320 --set rendering.height=240
```
