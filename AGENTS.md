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
