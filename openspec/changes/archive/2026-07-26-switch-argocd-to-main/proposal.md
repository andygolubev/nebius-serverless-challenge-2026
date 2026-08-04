## Why

The SaaS control plane currently tracks `main`, while the active deployment work is being
prepared on `main`. Argo CD must consistently use that branch without permitting
accidental commits or pushes to `main` during this temporary workflow.

## What Changes

- Repoint the repository-managed Argo CD child Applications and bootstrap defaults to
  `main`.
- Document the temporary branch policy: commits and pushes are allowed only on
  `main`, never on another branch.
- Define the manual live-cluster cutover and verification needed after the branch is pushed.

## Capabilities

### New Capabilities

- `main-gitops-source`: Safe, consistent Argo CD branch selection and manual cutover
  procedure for the temporary debug deployment source.

### Modified Capabilities

- `gitops-delivery`: The configured Git source revision for the root and child Applications
  changes from `main` to `main`.

## Impact

This affects `AGENTS.md`, the Argo CD Application manifests, OpenTofu/bootstrap revision
defaults, and the live root Application once its SSH host identity has been independently
verified. The cluster is not changed as part of the repository-only update.
