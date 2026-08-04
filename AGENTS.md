## Branch policy

Develop, commit, and push only on the `main` branch.

# Agent instructions

This repository uses OpenSpec to plan and implement changes. Before editing, inspect the active
change with `openspec list`, then follow the relevant proposal, design, specs, and tasks beneath
`openspec/changes/`. Use the matching OpenSpec skill and check off tasks only after verification.

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing system boundaries or cloud workflows.
Record progress, commands, observed results, blockers, and safe next steps in
`IMPLEMENTATION_LOG.MD` so another agent can resume without guessing. The log is a local handoff
artifact and is intentionally gitignored; never put credentials or secret selectors in it.
SSH access to the SaaS server uses user `saas-server` (not `ubuntu`) at
`sim-policy-trainer-challenge.info` / `195.242.13.73`, with the gitignored key
`ssh-keys/saas-server-key` and `-o IdentitiesOnly=yes`; `kubectl` on the box requires `sudo`.
Full details live in the log's "Operations: SaaS server access" section.

An authenticated `gh` CLI is available for this repository. Use it to check GitHub Actions runs
and logs (e.g. `gh run list --workflow saas-image.yml`, `gh run view <id> --log-failed`) instead
of guessing whether CI built or why it failed.

Before running any `tofu` command in `sim2policy/infra/nebius`, set up both auth layers in the
current shell — the S3 state backend and the Nebius provider use separate credentials:

```bash
source ~/.config/sim2policy/tofu-backend.env             # static key for the state bucket
export NEBIUS_IAM_TOKEN="$(nebius iam get-access-token)" # short-lived provider token
```

Missing the first causes `403 AccessDenied` acquiring the state lock; missing (or an expired)
second causes `PermissionDenied` on every resource refresh. The token expires, so re-export it in
each new session. If the state-bucket key itself has expired, reissue it per
`sim2policy/infra/nebius/README.md` (`nebius iam v2 access-key create` for the
`sim2policy-tfstate` service account).

Preserve unrelated worktree changes. Do not commit generated runs, checkpoints, logs, large media,
cloud credentials, Terraform/OpenTofu state, plans, or local environment files.

For authenticated SaaS UI API operations, follow `saas/API_RUNBOOK.md`. Never record a real bearer
token in Git, command examples, issue text, or `IMPLEMENTATION_LOG.MD`; respect explicit instructions
to keep or revoke the server-side UI session after the operation.

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
