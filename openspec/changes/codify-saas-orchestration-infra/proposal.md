## Why

The `nebius-job-orchestration` backend is implemented, but its required cloud identity, credentials delivery, Kubernetes configuration, and training image are still assembled through a manual CLI procedure. Codifying those prerequisites now makes the deployed SaaS path reproducible after infrastructure rebuilds and removes hand-copied identifiers and secret values from operator workflows.

## What Changes

- Provision a dedicated `sim2policy-saas-orchestrator` service account, isolate its required project-level `editor` grant, and attach it to the SaaS VM so the backend authenticates through instance metadata without a long-lived SDK credential.
- Export the complete non-secret and secret-selector contract needed to configure the `saas-nebius` Kubernetes Secret: versioned artifact selector, artifact access key ID and storage settings, subnet ID, project ID, registry pull selector, and SB3 job image reference.
- Automate or script idempotent synchronization of `saas-nebius` on the k3s server using the VM identity to resolve MysteryBox values, so secret material does not transit an operator command line or shell history.
- Add a GitHub Actions pipeline that builds the `sb3` target from `sim2policy/Dockerfile` and pushes immutable commit tags plus the `sb3-runtime` compatibility tag to the existing Nebius registry with the `sim2policy-saas-ci` credentials when `sim2policy/` changes.
- Replace the README's manual cloud setup procedure with OpenTofu output-driven instructions, correct the rebuilt subnet reference, and document the broad `editor` grant as a revisit point when Nebius provides a job-scoped role.

## Capabilities

### New Capabilities

- `saas-orchestration-infrastructure`: Reproducible OpenTofu resources, safe MysteryBox credential delivery, complete deployment outputs, and identity-based Kubernetes Secret synchronization for the Nebius SaaS orchestration backend.
- `training-runtime-image-pipeline`: CI build and registry publication of the SB3 Serverless AI training runtime using immutable revisions and the established CI service account.

### Modified Capabilities

<!-- No existing baseline capability requirements change. This proposal supplies cloud prerequisites for the active `nebius-job-orchestration` change. -->

## Impact

- **Infrastructure:** `sim2policy/infra/nebius/` OpenTofu resources, variables, outputs, cloud-init or a colocated sync script, and remote state managed with OpenTofu 1.12.3 / Nebius provider 0.6.22.
- **CI:** `.github/workflows/` gains or extends a registry build workflow using the existing `sim2policy-saas-ci` credentials and registry.
- **Operations:** the k3s `saas-nebius` Secret becomes derivable from infrastructure outputs and MysteryBox without exposing credential values; the project-level `editor` role remains confined to the new orchestrator account.
- **Documentation:** `sim2policy/infra/nebius/README.md`, `sim2policy/jobs/README.md`, and related examples stop relying on stale or hand-copied cloud IDs.
- **State/security:** credential values remain out of Git and, where provider write-only fields permit, out of Terraform state; selectors and non-secret IDs may be output for automation.
