# Sim2Policy training template

The data plane: a configuration-driven reinforcement-learning template that turns one training run
— local or as a Nebius Serverless AI Job — into durable checkpoints, evaluation metrics, reports,
and rollout media under a single run identity.

Read [ARCHITECTURE.md](../ARCHITECTURE.md) for system boundaries and the reasoning behind these
choices. This file is the operator's index.

## Two tracks

| | Track B (baseline) | Track A (GPU-native) |
| --- | --- | --- |
| Stack | Gymnasium MuJoCo + Stable-Baselines3 PPO | MuJoCo Playground / Brax PPO on MJX |
| Entry point | `sim2policy.train_sb3` | `sim2policy.train_mjx` |
| Image target | `sb3` | `mjx` |
| Dependency extra | `--extra sb3` | `--extra mjx` |
| Typical hardware | `cpu-d3` (CPU-vectorized) | `gpu-h100-sxm` |

Track B is the dependable path and ships first. Track A is isolated behind its own dependency group
and container target, so a JAX/CUDA incompatibility cannot make Track B unrunnable. Installing only
the SB3 extra keeps training, evaluation, rendering, and storage fully working without importing any
MJX package. Running an MJX command in an SB3 image exits with an actionable dependency diagnostic.

Pinned versions live in [VERSIONS.md](VERSIONS.md); `uv.lock` is the source of truth.

## Setup

```bash
uv sync --extra dev --extra api
```

Add `--extra sb3` or `--extra mjx` for a backend. `make setup` does the base install.

## Commands

Every target passes environment and run identity explicitly, so nothing requires a source edit.
`ENV` selects `configs/<ENV>.yaml`; `RUN_ID` names the run tree.

```bash
make check                                   # ruff + mypy
make test                                    # pytest
make build-sb3 IMAGE=sim2policy:sb3          # backend-isolated image targets
make build-mjx IMAGE=sim2policy:mjx
make smoke ENV=smoke_sb3 RUN_ID=dev          # ten-frame render, no checkpoint needed
make train ENV=halfcheetah_sb3 RUN_ID=hc-01
make evaluate ENV=halfcheetah_sb3 RUN_ID=hc-01 CHECKPOINT=runs/hc-01/checkpoints/final.zip
make render   ENV=halfcheetah_sb3 RUN_ID=hc-01 CHECKPOINT=runs/hc-01/checkpoints/final.zip
make report   ENV=halfcheetah_sb3 RUN_ID=hc-01
make api BACKEND=mock                        # the demo API on 127.0.0.1:8000
make cloud-dry-run ENV=go1_mjx RUN_ID=go1-01 # preview a Nebius submission, secrets redacted
make cloud-train   ENV=go1_mjx RUN_ID=go1-01
```

Run gates in increasing cost order: local tests → image health and import checks → render smoke →
short GPU/CPU job with an explicit timeout → bounded training with storage sync → resume drill →
full run. Confirm CUDA/JAX discovery and durable artifact upload before starting full training.

## The run contract

`configs/*.yaml` declares backend, environment, seed, training budget, parallelism, checkpoint
cadence, evaluation settings, success threshold, and backend-specific hyperparameters. CLI flags
select the config and supply run identity or narrowly scoped overrides. Invalid, missing, or
incompatible values are rejected *before* an expensive job is created.

Each run writes to `runs/<run_id>/` while it executes:

```
runs/<run_id>/
├── metadata/status.json          queued → starting → training → rendering → evaluating → completed | failed
├── metadata/request.json
├── checkpoints/                  initial, periodic, final; latest.json advances only after a complete upload
├── tensorboard/
├── videos/{untrained,mid,final,progression_montage}.mp4
└── report/{metrics.json,report.md,artifacts.json}
```

Those four subdirectories map to the same subpaths under
`s3://<bucket>/sim2policy/<run_id>/`, which is canonical across ephemeral jobs. Set the bucket,
endpoint, region **and** `storage.mode: s3` together — an `ArtifactStore` is inert while the mode is
`local`, so a half-configured destination trains for its full budget and durably writes nothing.

Resume is explicit: it finds the latest completed checkpoint, validates backend/environment/config
compatibility, downloads it, and continues from the recorded step. An incompatible checkpoint fails
before training rather than silently restarting the counter. With `jobs/submit.sh`, set
`RESUME=remote` with the same `RUN_ID` and config.

## Configs

| Config | Backend | Purpose |
| --- | --- | --- |
| `smoke_sb3.yaml` | SB3 | Fast local smoke |
| `halfcheetah_sb3.yaml`, `ant_sb3.yaml`, `hopper_sb3.yaml`, `walker2d_sb3.yaml`, `reacher_sb3.yaml` | SB3 | Classic MuJoCo baselines |
| `*_gallery_sb3.yaml` | SB3 | Curated showcase workloads |
| `go1_mjx.yaml` | MJX | `Go1JoystickFlatTerrain` quadruped |
| `g1_flat_mjx.yaml` | MJX | `G1JoystickFlatTerrain` humanoid |
| `g1_forward_flat_mjx.yaml`, `g1_forward_rough_mjx.yaml` | MJX | Fixed-forward G1 curriculum phases |
| `training_presets.yaml` | — | Demo API allowlist |
| `showcase_training_matrix.yaml` | — | Curated campaign contract |

## Rendering and evaluation

Rendering and evaluation are separate commands over a checkpoint plus resolved run metadata, so a
graphics failure cannot invalidate training and media can be produced on a different machine. The
renderer tries EGL first and retries once with OSMesa **in a fresh process**, because MuJoCo's
graphics-backend selection is process-global; it reports which backend produced the output.
`--smoke-test` renders and validates at least ten frames without a trained checkpoint.

Evaluation defaults to 20 deterministic episodes across five seeds and takes its success criterion
from the resolved config — a mean-reward threshold for SB3, sustained velocity and non-fall
conditions for MJX locomotion. It writes `report/metrics.json` (schema:
[`docs/metrics.schema.json`](docs/metrics.schema.json)) plus a Markdown report with the reward curve
and time-to-threshold. Cost is measured runtime times an explicit timestamped rate; an unavailable
utilization or price input is marked unavailable, never invented.

## Demo API

`sim2policy.api` is a thin, stateless FastAPI layer — `GET /health`, `GET /training-options`,
`POST /train`, `GET /runs/{run_id}`, `GET /runs/{run_id}/artifacts`. It never trains: it validates
against the preset allowlist, generates a safe `run_id`, persists the request and an initial status,
and triggers an orchestration backend (`mock` or `nebius`). All status and artifact responses are
read back from object storage, so instances hold no run state and a mock run is observed exactly
like a real job. Artifact URLs are presigned and scoped to the run prefix. A configurable demo token
gates the mutating endpoints; `/health` stays open and reports the active backend so an operator can
confirm whether real jobs will be launched.

`configs/training_presets.yaml` **is** the allowlist. Each preset pins backend, environment,
algorithm, base run-config, and hard step/duration limits, and declares the small set of safe
overridable parameters with bounds. Nothing else is accepted — no environment IDs, images, commands,
code paths, or reward functions. `halfcheetah-demo`, `ant-demo`, and `ant-quality` are enabled;
`go1-mjx-demo` is present but disabled, hidden from `/training-options` and rejected by `POST /train`
while its flag is off.

This demo API is the data-plane surface and is distinct from the tenant SaaS app in [`../saas/`](../saas/),
which has its own authenticated API and SDK-based orchestration. Full reference:
[`docs/api.md`](docs/api.md).

## Cloud submission

[`jobs/submit.sh`](jobs/README.md) is the validated Nebius boundary. It requires `IMAGE`, `CONFIG`,
`RUN_ID`, `PLATFORM`, `PRESET`, `TIMEOUT`, and `SUBNET_ID`, builds an argument array without
evaluating user-supplied values, enforces the mandatory timeout, and accepts MysteryBox secret
selectors through `REGISTRY_SECRET` and `S3_SECRET` without printing them. `DRY_RUN=1` prints a
safely escaped, redacted command and creates nothing.

Infrastructure lives in [`infra/nebius/`](infra/nebius/README.md): registry, bounded/versioned
artifact bucket, least-privilege artifact identity, and the `saas-server` control plane. Serverless
jobs stay explicit submissions rather than managed resources.

## Further reading

- [`docs/submission-checklist.md`](docs/submission-checklist.md) — verified runs and artifact references
- [`docs/demo-script.md`](docs/demo-script.md) — walkthrough for a live demo
- [`docs/custom-robot-training-contract.md`](docs/custom-robot-training-contract.md) — generic
  custom-robot runtime, task, and profile contract shared with the SaaS backend
- [`docs/release-audit.md`](docs/release-audit.md) — release verification record
- [`assets/samples/`](assets/samples/) — lightweight sample reward curves and teaser media (large
  checkpoints, logs, and full videos stay out of Git)
