## Context

Argo CD's desired Git source is temporarily `main`, but the SaaS image workflow has a hard-coded `main` trigger, stale-SHA check, checkout, and push target. That disconnect leaves the manifest's immutable image reference unchanged when the deployment branch advances.

## Goals / Non-Goals

**Goals:**

- Build and publish a SaaS image for relevant `main` pushes.
- Commit the resulting immutable image tag back to `main` only after confirming the branch did not advance during the build.
- Keep the default-branch workflow behavior intact for future restoration.

**Non-Goals:**

- Push, merge, or mutate `main`.
- Change registry credentials, Argo CD credentials, or the SaaS application's runtime configuration.
- Bypass SSH host-key verification for the live-cluster cutover.

## Decisions

- **Permit both `main` and `main` workflow triggers, but gate the GitOps bump to the configured deployment branch.** This preserves normal default-branch builds while making the temporary branch authoritative for GitOps.
- **Derive stale-ref verification, checkout, and push target from `GITHUB_REF_NAME`.** On a push, this is the branch that produced the image, preventing a stale build from overwriting a newer image tag on that branch.
- **Assert the branch contract in the existing shell check.** The check verifies the deployment-bump condition, dynamic stale branch check, and branch-targeted push.

## Risks / Trade-offs

- [A `main` push builds but does not advance GitOps] → This is intentional under the temporary branch policy.
- [A newer main commit lands during the build] → The stale-ref guard exits without a deployment bump.
- [The live root Application still tracks main] → Perform the separate root-Application cutover only after the SSH host identity is independently verified.

## Migration Plan

1. Update and validate the workflow and assertion on `main`.
2. Commit and push only `main`; a qualifying push triggers the image workflow.
3. Confirm the workflow pushes an immutable image and its bot commit updates the GitOps image tag on `main`.
4. After verified SSH access, update and sync the live root Application to the same branch, then verify Argo CD and the SaaS workload.
5. Roll back by reverting the workflow commit on `main`; do not alter other branch refs.
