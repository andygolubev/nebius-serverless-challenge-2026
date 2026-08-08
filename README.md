# Sim2Policy

Sim2Policy is a project for the **Nebius Serverless Challenge 2026**. It trains robot locomotion
policies in simulation and turns each training run into reusable checkpoints, metrics, and rollout
videos.

## The problem

Training robot policies requires substantial compute, careful experiment tracking, and a reliable
way to preserve results after temporary training machines stop. Running this workflow locally is
often slow, expensive, and difficult to reproduce.

## The solution

Sim2Policy uses MuJoCo simulation and reinforcement learning to train robots without physical
hardware. Training runs as a Nebius Serverless AI Job while artifacts are stored in durable object
storage. A web application shows a read-only gallery of verified runs to anyone, and gives signed-in
users a guided flow to upload a robot model, compose a task and scene from server-owned options,
validate it, and train it.

The project supports both Stable-Baselines3 for dependable CPU training and MJX/JAX for GPU-parallel
simulation.

## What is inside

| Path | Contents |
| --- | --- |
| [`sim2policy/`](sim2policy/README.md) | Training, evaluation, rendering, job submission, cloud infrastructure |
| [`saas/`](saas/README.md) | FastAPI + React application for the public showcase and custom-robot training |
| [`deploy/`](deploy/README.md) | Kubernetes and ArgoCD state reconciled onto the cluster |
| [`openspec/specs/`](openspec/specs/) | Behavioural requirements, one directory per capability |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System boundaries, design decisions, and their rationale |
| [`AGENTS.md`](AGENTS.md) | Working agreements and cloud cost rules |

Start with [ARCHITECTURE.md](ARCHITECTURE.md) — it explains how the two planes fit together and why
each boundary is where it is, and points at the more detailed document for every area.
