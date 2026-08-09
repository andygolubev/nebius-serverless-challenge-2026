<div align="center">

# 🤖 Sim2Policy

### Train a robot to walk — from your browser, on serverless GPUs, for pocket change.

[![Live demo](https://img.shields.io/badge/live%20demo-sim--policy--trainer--challenge.info-2ea44f?style=for-the-badge)](https://sim-policy-trainer-challenge.info)

[![Nebius Serverless Challenge 2026](https://img.shields.io/badge/Nebius-Serverless%20Challenge%202026-0b7fff)](https://nebius.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-3776ab)](sim2policy/pyproject.toml)
[![MuJoCo](https://img.shields.io/badge/sim-MuJoCo%20%2B%20MJX-ff6f00)](https://mujoco.org)
[![PPO](https://img.shields.io/badge/RL-PPO%20(SB3%20%2F%20Brax)-8a2be2)](sim2policy/README.md)

<img src="docs/images/hero.jpg" alt="Sim2Policy — watch robots learn to move" width="900">

</div>

---

## Why it exists

Serverless GPUs are easy to start and easy to lose. A job spins up, trains, disappears — and takes
the evidence with it. **Sim2Policy makes every run outlive its machine.**

Each training job leaves behind a durable, reproducible result in object storage:

🧠 **A trained checkpoint** · 🎬 **Rollout video** (wobbling → walking) · 📊 **Deterministic
evaluation** · 📦 **A policy bundle** with config, versions, and checksums

## Seven policies. $4.35.

Every number below is read live from the deployed gallery — observed on the job itself, not estimated.

| Run | Backend | Steps | Duration | Cost | Result |
| --- | --- | --: | --: | --: | --- |
| **Go1 Walker** | MJX · H100 | 200,000,000 | 16m 48s | **$0.83** | ✅ velocity 0.97 ≥ 0.5 |
| G1 Rough Terrain | MJX · H100 | 348,651,520 | 2h 05m | $3.24 | ⚠️ published as a recording, criterion not met |
| Walker2D Stride | SB3 · CPU | 5,000,000 | 29m 30s | $0.10 | ✅ reward 5,314 ≥ 1,800 |
| Hopper Balance | SB3 · CPU | 5,000,000 | 21m 00s | $0.07 | ✅ reward 3,632 ≥ 1,000 |
| Ant Explorer | SB3 · CPU | 3,000,000 | 21m 36s | $0.07 | ✅ reward 2,975 ≥ 1,000 |
| HalfCheetah Sprint | SB3 · CPU | 3,000,000 | 12m 42s | $0.04 | ✅ reward 3,332 ≥ 1,500 |
| Reacher Target | SB3 · CPU | 1,000,000 | 2m 54s | **$0.01** | ✅ reward −5.6 ≥ −10 |

Real GPU reinforcement learning at coffee-money prices — and the one run that missed its bar is
published saying so, rather than quietly dropped.

## Pick an example, press go

Seven curated robots, from a two-link `Reacher` on CPU to the **Go1 quadruped** and **G1 humanoid**
on an H100. Anonymous visitors browse the whole gallery — real videos, real numbers, no account.

<img src="docs/images/gallery.jpg" alt="The Sim2Policy gallery: seven verified training runs" width="900">

## Every run ends in evidence

Success criterion, primary metric, observed duration and cost, the rollout video, the full
evaluation, and a one-click policy bundle — all bound to the exact acceptance revision.

<img src="docs/images/run-detail.jpg" alt="Go1 Walker result page: KPIs, rollout video, and evaluation" width="900">

## Bring your own robot

Sign in with an email code, upload a bounded MJCF model, then compose a setup from **server-owned**
tasks and scenes. A bounded CPU job verifies the robot actually compiles, renders, and trains before
the Start Training button unlocks.

<img src="docs/images/custom-robot.jpg" alt="Environment builder: pick a locomotion task, a scene preset, and bounded objects" width="900">

> You get choices, not footguns: no uploaded reward code, no scene XML, no remote URLs — and the
> backend, image, GPU shape, and command stay locked server-side.

## How it works

```mermaid
flowchart LR
    U["🧑 Browser"] -->|HTTPS| S["SaaS app<br/>FastAPI + React"]
    S --> J["Nebius Serverless AI Job<br/>ephemeral H100 / L40S / CPU"]
    J --> B{"Backend"}
    B -->|CPU| SB3["Gymnasium MuJoCo<br/>+ Stable-Baselines3 PPO"]
    B -->|GPU| MJX["MuJoCo Playground / Brax<br/>PPO on MJX + JAX"]
    SB3 --> O[("S3 object storage<br/>checkpoints · videos · metrics")]
    MJX --> O
    O --> S
    GA["GitHub Actions"] --> REG["Nebius registry"] --> AR["ArgoCD on k3s"] --> S
```

One tiny always-on VM runs the app and launches disposable jobs; **all the heavy lifting is
serverless**. Checkpoints stream to S3 as training progresses, so an interrupted job resumes instead
of restarting. Infrastructure is OpenTofu, delivery is GitOps, and no secret ever touches Git.

**Stack:** MuJoCo · MJX/JAX · Stable-Baselines3 · Brax · FastAPI · React + Vite · SQLite ·
Docker · k3s · ArgoCD · OpenTofu · Nebius Serverless AI

## Run it locally

```bash
cd sim2policy && uv sync --extra dev --extra sb3
```

```bash
make smoke ENV=smoke_sb3 RUN_ID=dev
```

```bash
make train ENV=halfcheetah_sb3 RUN_ID=hc-01 && make report ENV=halfcheetah_sb3 RUN_ID=hc-01
```

Gates run in increasing cost order — local tests → image checks → render smoke → bounded job → full
run. `make cloud-dry-run` previews a Nebius submission with every secret redacted.

## What's inside

| Path | Contents |
| --- | --- |
| [`sim2policy/`](sim2policy/README.md) | Training template: two backends, evaluation, rendering, job submission, OpenTofu infra |
| [`saas/`](saas/README.md) | FastAPI + React app: public showcase, auth, custom-robot flow |
| [`deploy/`](deploy/README.md) | Kubernetes + ArgoCD state reconciled onto the cluster |
| [`openspec/specs/`](openspec/specs/) | Behavioural contract — one directory per capability |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System boundaries, design decisions, and their rationale |

**Start with [ARCHITECTURE.md](ARCHITECTURE.md)** — it explains how the two planes fit together, why
each boundary sits where it does, and points at the detailed document for every area.

---

<div align="center">

Built for the **Nebius Serverless Challenge 2026** · MIT licensed · `#NebiusServerlessChallenge`

**[Try it live (till the End of August 2026) →](https://sim-policy-trainer-challenge.info)**

</div>
