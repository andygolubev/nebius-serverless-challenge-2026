## Branch policy

Develop, commit, and push only on the `main` branch.

# Agent instructions

This repository uses OpenSpec. `openspec/specs/` holds the behavioural contract — one directory per
capability, each stating requirements and the scenarios that verify them. Read the spec for any
capability you touch and keep it true; a behaviour change is a spec change. Active work goes under
`openspec/changes/<change-id>/` (proposal, design, specs, tasks) via the matching OpenSpec skill;
check off tasks only after verification. Historical changes were consolidated into
[ARCHITECTURE.md](ARCHITECTURE.md) and the READMEs and remain in Git history.

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing system boundaries or cloud workflows. It is
the source of truth for how the system is put together and why, and its "Where things are
documented" table points at the detailed document for each area.
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
running after the work that needed them completes, so they stop incurring cost.

Images are built in CI; VMs are for GPU execution and orchestration only:

- **Build SB3 and MJX images in GitHub Actions, never on a VM.** Pushing a commit that touches
  `sim2policy/**` runs the `training-runtime-images` workflow, which matrixes both targets and
  pushes immutable `sb3-<sha>` / `mjx-<sha>` tags to the project registry. Promotion to the GitOps
  deployment is a separate `workflow_dispatch` with `promote: true`; a campaign never needs it,
  because it pins by digest. Do not spend GPU — or any VM — time compiling or packaging containers.
- Submit that exact immutable tag or digest. Never replace a tag used by a running job. Obtain
  registry and artifact settings from the existing OpenTofu outputs under `sim2policy/infra/nebius`;
  do not copy secrets into commands, documentation, images, or the implementation log.
- Use the single-GPU H100 `gpu-h100-sxm` / `1gpu-16vcpu-200gb` preset only for MJX/JAX accelerator
  smoke tests, profiling, and Track A training. SB3 PPO is primarily CPU-bound here; use CPU or the
  cheaper validated L40S path for Track B instead of H100.
- Run gates in increasing cost order: local tests, image health/import checks, a short GPU smoke
  job with an explicit timeout, bounded training, then a full run. Confirm CUDA/JAX discovery and
  durable artifact upload before starting full training.
- Stop or delete the H100 immediately after the job and artifact checks finish. Audit instances,
  disks, public IPs, temporary security rules, and failed AI jobs after each cloud session.
- CI may push a new immutable image while a GPU job runs an older digest. Record image digest,
  non-secret VM/job identifiers, commands, results, cleanup, and the next safe action in
  `IMPLEMENTATION_LOG.MD`.
