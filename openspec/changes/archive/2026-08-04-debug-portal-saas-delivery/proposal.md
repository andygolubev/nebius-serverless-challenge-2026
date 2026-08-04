## Why

The SaaS image workflow only builds and advances GitOps state for `main`, while Argo CD is
temporarily intended to follow `debug-portal`. Consequently, commits to the deployment branch do
not produce a deployable image or update the immutable image selected by the SaaS manifest.

## What Changes

- Trigger the SaaS image workflow for qualifying pushes to `debug-portal`.
- Restrict the workflow's image-tag GitOps bump and stale-revision guard to the branch that
  triggered the push, so it updates `debug-portal` without mutating `main`.
- Update the deployment-workflow assertion to verify the temporary branch policy.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `saas-image-pipeline`: Successful qualifying pushes to the temporary deployment branch build an
  immutable SaaS image and advance that branch's GitOps image tag.
- `gitops-delivery`: The debug-portal GitOps source can receive its matching immutable image tag
  without a write to `main`.

## Impact

This changes `.github/workflows/saas-image.yml` and its repository assertion. It allows GitHub
Actions to commit only to `debug-portal`; the live Argo root-Application cutover remains a
separate, host-key-verified operator action.
