## Context

The active `nebius-job-orchestration` change has implemented and locally verified the SaaS backend's Nebius SDK path. Its remaining cloud prerequisites are described as an operator-run CLI procedure in `sim2policy/infra/nebius/README.md`: create a privileged service account and key, copy the key into MysteryBox, assemble `saas-nebius`, and separately build the training image. That procedure is not reproducible after a rebuild and puts secret resolution too close to an interactive shell.

The current stack already establishes the patterns to extend: OpenTofu 1.12.3 with Nebius provider 0.6.22 and remote state, `nebius_iam_v2_access_key` using `secret_delivery_mode = "MYSTERY_BOX"`, outputs for MysteryBox selectors, a dedicated `sim2policy-saas-ci` registry pusher, and k3s cloud-init that resolves secrets through the VM service-account identity. The verified project is `project-e00wkbbppr00tab5fhhmz7`; the rebuilt subnet is `vpcsubnet-e00re7tmw1apqd4pmm`. Existing artifact and registry credentials are imported/referenced rather than recreated.

## Goals / Non-Goals

**Goals:**

- Make a fresh OpenTofu apply produce the dedicated orchestration identity, its isolated access grant, and a MysteryBox-delivered authentication credential without committing or printing credential values.
- Make every value needed by `saas-nebius` machine-consumable from stable OpenTofu outputs, including secret selectors with explicit versions.
- Reconcile `saas-nebius` on the k3s host without sending resolved secrets through an operator's shell.
- Ensure every relevant `sim2policy/` revision can publish an SB3 training runtime under an immutable tag, while preserving the backend's configured `sb3-runtime` compatibility reference.
- Make documentation reflect the rebuilt resources and the automated workflow.

**Non-Goals:**

- Changing the SaaS backend's orchestration behavior or environment variable names.
- Creating or running Serverless AI jobs during `tofu apply` or CI.
- Replacing the existing artifact access key, registry pull token, registry, subnet, or SaaS CI identity.
- Building MJX images or performing GPU validation in GitHub Actions.
- Expanding the new orchestrator service account beyond the project-level role currently required by Nebius.

## Decisions

### 1. Model the orchestrator identity separately and deliver its key directly to MysteryBox

Add a dedicated `nebius_iam_v1_service_account` named `sim2policy-saas-orchestrator`, a project access binding/permit granting `editor`, and the provider's service-account authentication-key resource configured for MysteryBox delivery. The exact 0.6.22 resource schema and write-only argument must be confirmed from the installed provider schema before implementation; the resulting state must be inspected structurally to ensure no private key payload is retained.

This identity is intentionally separate from `sim2policy-saas-server`, `sim2policy-saas-ci`, and `sim2policy-artifacts`. Reusing any of those accounts would couple unrelated privileges and make later replacement of `editor` harder. Manually creating the key and importing only a selector was rejected because it preserves an undocumented lifecycle step.

### 2. Treat secret selectors as deployment interfaces, not resolved secret values

Expose scalar outputs for the orchestrator service-account ID, orchestrator credential selector, versioned artifact secret selector, artifact access key ID, storage endpoint/region/bucket, project ID, subnet ID, registry pull secret selector, and SB3 image reference. Also expose a non-sensitive object output representing the `saas-nebius` source contract when that improves scripting without duplicating values.

Selectors must include an immutable secret-version component where the consumer or SDK requires `secret_id/version_id`. Existing resources whose status returns an unversioned reference must be joined with their provider-exposed version, or accept explicit existing secret/version inputs. OpenTofu outputs never resolve MysteryBox payloads. Hard-coded IDs remain only in gitignored environment inputs/backend configuration, not copied through README commands.

### 3. Reconcile the Kubernetes Secret on the server using VM identity

Extend the existing cloud-init bootstrap with a root-owned, idempotent sync script and systemd unit (or, if cloud-init size/ordering makes that unsafe, add the same script under `sim2policy/infra/nebius/scripts/` and install/invoke it from cloud-init). The script obtains a short-lived token from instance metadata, fetches the selected MysteryBox versions, writes temporary credential material only to a mode-`0600` root-owned file or pipe, and applies `saas-nebius` via `kubectl create secret ... --dry-run=client -o yaml | kubectl apply -f -`. Cleanup traps remove temporary files.

OpenTofu template inputs contain selectors and non-secret settings only. The unit runs after k3s is ready, can be rerun after secret rotation, and fails closed without echoing response bodies or values. A purely documented operator command is retained only as a break-glass path because it cannot meet the shell-history requirement as reliably.

### 4. Publish an immutable SB3 image and deliberately update the compatibility tag

Add a focused workflow triggered by pushes to `main` that touch `sim2policy/**` or the workflow itself, plus manual dispatch. It builds `sim2policy/Dockerfile` with target `sb3`, authenticates via the existing masked registry/token repository secrets used by `sim2policy-saas-ci`, and pushes both `sim2policy:<full-or-short-commit-sha>` and `sim2policy:sb3-runtime` from the same build result. The workflow reports the resulting digest.

The commit tag is the reproducible deployment/debugging reference. `sb3-runtime` is an explicit compatibility tag because the current SaaS contract consumes that output; it is updated only after the immutable push succeeds. Pull requests may build/test without pushing if useful, but untrusted contexts receive no registry credentials. Reusing the SaaS image workflow was rejected because the contexts, Dockerfiles, target names, and path triggers differ.

### 5. Validate without submitting a paid workload

Implementation verification proceeds through formatting, `tofu validate`, provider-schema inspection, a reviewed remote-state plan, workflow syntax/build validation, and a k3s secret-sync dry run that inspects keys and selectors but never prints values. A real Serverless AI job remains the final gate owned by `nebius-job-orchestration` task 6.3 after the runtime image exists.

## Risks / Trade-offs

- [Project `editor` allows broader mutations than job submission] → isolate it to the new non-interactive account, deliver the key only through MysteryBox, document the exception, and make replacement with a future job-scoped role a named follow-up.
- [Provider authentication-key support may retain sensitive material in state] → inspect provider 0.6.22 schema and a redacted plan/state shape before apply; use write-only/MysteryBox delivery fields and stop if the private credential would be persisted.
- [Cloud-init changes can replace or disrupt the SaaS VM] → inspect the plan, prefer an idempotent script/unit, and separate infrastructure apply from secret reconciliation where replacement is indicated.
- [A moving `sb3-runtime` tag can make deployments non-reproducible] → always publish and log an immutable commit tag/digest first; keep the moving tag solely for the existing compatibility contract and allow pinning the OpenTofu job-image input later.
- [Secret rotation can leave Kubernetes stale] → make the sync unit rerunnable and document the rotate-then-sync procedure; versioned selectors ensure the chosen revision is explicit.
- [Workflow changes under broad `sim2policy/**` paths may rebuild frequently] → use BuildKit cache and concurrency cancellation while retaining the requested correctness-first trigger.

## Migration Plan

1. Confirm provider 0.6.22 schemas and existing remote-state/resource addresses; add resources and inputs without applying.
2. Add outputs and the secret-sync mechanism, then run formatting, validation, template checks, and a reviewed remote-state plan. Verify the plan neither replaces unrelated infrastructure nor contains credential payloads.
3. Apply the infrastructure in the configured remote backend, record only non-secret resource IDs/selectors, and run the k3s sync unit. Verify `saas-nebius` contains the expected key names without displaying their values.
4. Merge/dispatch the runtime image workflow, verify both tags resolve to the same digest, and retain the immutable digest in the implementation log.
5. Update docs and hand off to `nebius-job-orchestration` for its bounded end-to-end smoke test.

Rollback disables the Nebius backend or restores the prior `saas-nebius`, removes the sync unit, and reverts the compatibility image tag to a known immutable digest. Destroying the orchestrator key/account is a final explicit step after the backend is no longer using it; unrelated registry, artifact, and SaaS-server resources remain untouched.

## Open Questions

- Which exact Nebius provider 0.6.22 resource creates an SDK-compatible service-account credentials JSON with direct MysteryBox delivery, and which status attributes expose its secret ID and primary version?
- Does the existing registry pull token input provide a versioned selector, or must the stack add a separate version input/output to satisfy the SDK/Kubernetes consumer contract?
- Should the job image output remain the `sb3-runtime` compatibility tag or accept an optional immutable tag/digest variable as the production default after CI publishes its first image?
