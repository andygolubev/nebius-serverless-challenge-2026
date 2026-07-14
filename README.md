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
hardware. Training can run as a Nebius Serverless AI Job, while artifacts are stored in durable
object storage. A small web application provides ready-to-run examples and a guided flow for
validating and training custom robot models.

## What is inside

- `sim2policy/` — training, evaluation, rendering, job submission, and cloud infrastructure.
- `saas/` — the FastAPI and React application for launching and reviewing training runs.
- `deploy/` — Kubernetes and ArgoCD deployment configuration.
- `openspec/` — project proposals, specifications, designs, and implementation tasks.
- `ARCHITECTURE.md` — the detailed system architecture and technical boundaries.

The project supports both Stable-Baselines3 for dependable CPU training and MJX/JAX for
GPU-parallel simulation.
