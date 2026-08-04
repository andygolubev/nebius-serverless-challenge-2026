## Why

The SaaS control plane currently tracks `main`, while the active deployment work is being
prepared on `debug-portal`. Argo CD must consistently use that branch without permitting
accidental commits or pushes to `main` during this temporary workflow.

## What Changes

- Repoint the repository-managed Argo CD child Applications and bootstrap defaults to
  `debug-portal`.
- Document the temporary branch policy: commits and pushes are allowed only on
  `debug-portal`, never on `main`.
- Define the manual live-cluster cutover and verification needed after the branch is pushed.

## Capabilities

### New Capabilities

- `debug-portal-gitops-source`: Safe, consistent Argo CD branch selection and manual cutover
  procedure for the temporary debug deployment source.

### Modified Capabilities

- `gitops-delivery`: The configured Git source revision for the root and child Applications
  changes from `main` to `debug-portal`.

## Impact

This affects `AGENTS.md`, the Argo CD Application manifests, OpenTofu/bootstrap revision
defaults, and the live root Application once its SSH host identity has been independently
verified. The cluster is not changed as part of the repository-only update.
