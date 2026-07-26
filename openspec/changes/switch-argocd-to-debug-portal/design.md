## Context

The k3s control plane bootstraps a root Argo CD Application from an OpenTofu cloud-init
template. That root reads `deploy/argocd`, whose child Applications currently also pin
`main`. The active development and temporary deployment branch is `debug-portal`.

## Goals / Non-Goals

**Goals:**

- Make every repository-managed Argo CD source revision use `debug-portal`.
- Prevent an accidental `main` commit or push while this temporary workflow is active.
- Provide a safe manual cutover procedure for the existing cluster.

**Non-Goals:**

- Change the running cluster during the repository update.
- Alter Argo CD credentials, namespaces, applications, sync policy, or workload manifests.
- Rewrite history, merge `debug-portal` into `main`, or commit/push any `main` ref.

## Decisions

- **Update the root and child source revisions.** The root Application must be repointed
  manually to make the live cluster read `deploy/argocd` from `debug-portal`; child manifests
  on that branch then keep their own source revisions aligned. Updating only children cannot
  switch a root that still tracks `main`.
- **Preserve bootstrap consistency.** The OpenTofu variable default, example input, and the
  configured ignored `saas.auto.tfvars` use `debug-portal` so a future server recreation does
  not revert to `main`.
- **Require independent SSH host-key verification before live access.** The server's presented
  host key conflicts with the local `known_hosts` record. Do not bypass strict host checking or
  replace the entry until an operator verifies the new fingerprint out of band.
- **Push only after validation.** Commit and push the existing `debug-portal` branch, explicitly
  using `origin debug-portal`; no `main` ref is read as a push target or mutated.

## Risks / Trade-offs

- [A branch is absent on the remote] → Verify/push `debug-portal` before live cutover so Argo CD
  can resolve it.
- [The cluster could resolve a stale revision during transition] → Refresh and sync the root App,
  then verify root, child, and workload Sync/Health status.
- [A host-key change could indicate a security issue] → Stop before any SSH connection until the
  operator confirms the new identity.
- [The temporary policy becomes stale] → Its explicit wording and OpenSpec record make the
  temporary restriction visible for later removal by an authorized change.

## Migration Plan

1. Validate and push the repository change on `debug-portal` only.
2. Verify the server SSH key fingerprint out of band and repair the local trust record only after
   verification.
3. Manually update the live root Application's `spec.source.targetRevision` to `debug-portal`.
4. Refresh/sync it and confirm root/child Applications are Synced and Healthy and the SaaS
   workload is healthy.
5. Roll back, if necessary, by manually setting the root Application and repository revision
   fields back to the previously verified revision; do not use this change to push to `main`.
