# Agent instructions

This repository uses OpenSpec to plan and implement changes. Before editing, inspect the active
change with `openspec list`, then follow the relevant proposal, design, specs, and tasks beneath
`openspec/changes/`. Use the matching OpenSpec skill and check off tasks only after verification.

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing system boundaries or cloud workflows.
Record progress, commands, observed results, blockers, and safe next steps in
`IMPLEMENTATION_LOG.MD` so another agent can resume without guessing. The log is a local handoff
artifact and is intentionally gitignored; never put credentials or secret selectors in it.

Preserve unrelated worktree changes. Do not commit generated runs, checkpoints, logs, large media,
cloud credentials, Terraform/OpenTofu state, plans, or local environment files.

## Nebius build and GPU workflow

**Always stop or delete every VM once its task is done.** Do not leave GPU or CPU instances
running after the work that needed them completes — stop the CPU builder when its cached disk is
still useful, and delete instances you no longer need so they stop incurring cost.

Use separate machines for image construction and GPU execution:

- Build SB3 and MJX images on a reusable `cpu-d3` VM in `eu-north1`, normally
  `8vcpu-32gb` or `16vcpu-64gb` with a 300–500 GiB managed SSD. Use Docker BuildKit, preserve its
  layer cache between iterations, and push the finished image to the project registry. Do not spend
  GPU time compiling or packaging containers.
- Tag every pushed image with the Git commit SHA (or another immutable revision) and submit that
  exact tag or digest. Never replace a tag used by a running job. Obtain registry and artifact
  settings from the existing OpenTofu outputs under `sim2policy/infra/nebius`; do not copy secrets
  into commands, documentation, images, or the implementation log.
- Use the single-GPU H100 `gpu-h100-sxm` / `1gpu-16vcpu-200gb` preset only for MJX/JAX accelerator
  smoke tests, profiling, and Track A training. SB3 PPO is primarily CPU-bound here; use CPU or the
  cheaper validated L40S path for Track B instead of H100.
- Run gates in increasing cost order: local tests, image health/import checks, a short GPU smoke
  job with an explicit timeout, bounded training, then a full run. Confirm CUDA/JAX discovery and
  durable artifact upload before starting full training.
- Keep the CPU builder stopped when inactive if its cached disk is still useful. Stop or delete the
  H100 immediately after the job and artifact checks finish. Audit instances, disks, public IPs,
  temporary security rules, and failed AI jobs after each cloud session.
- The builder may push a new immutable image while a GPU job runs an older digest. Record image
  digest, non-secret VM/job identifiers, commands, results, cleanup, and the next safe action in
  `IMPLEMENTATION_LOG.MD`.
