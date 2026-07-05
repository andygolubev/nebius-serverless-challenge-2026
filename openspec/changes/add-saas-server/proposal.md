## Why

Sim2Policy today exposes training only as a fixed-preset demo API run by hand. To make it useful to
other scientists, it needs a durable, always-on **SaaS control plane**: a place tenants visit to
submit jobs and retrieve results, deployed and updated automatically instead of by ad-hoc `make`
commands. This change adds the always-on server, the GitOps delivery path that keeps it up to date,
and a first (mock-backed) tenant-facing app so the surface can be exercised end to end before real
multi-tenant GPU execution is wired in.

## What Changes

- Add a long-lived `saas-server` CPU VM to the Nebius Terraform (`sim2policy/infra/nebius/`) with a
  dedicated service account, static public IP, and a cloud-init script that installs **k3s**
  (single-node Kubernetes) and bootstraps **ArgoCD**.
- Provision **MysteryBox** secrets and least-privilege IAM so ArgoCD can read a **GitHub token** (to
  pull the app manifests / private repo) and a **Nebius Registry** pull credential — the latter only
  if registry access cannot be granted to the VM's service account by IAM role (documented decision
  in design.md).
- **Restrict network access** to the `saas-server` to only what is necessary: inbound **SSH (22)**
  and **HTTPS (443)** (plus HTTP/80 only for ACME/redirect). The Kubernetes API server and ArgoCD
  admin UI are **not** exposed publicly — the operator manages the cluster over an **SSH tunnel**
  (`kubectl`/ArgoCD bound to localhost, reached via `ssh -L`).
- Add a **GitHub Actions** pipeline that builds the SaaS app container and pushes it to the existing
  Nebius Registry, including the documented **registry authentication** method for CI.
- Add a GitOps repository layout (ArgoCD `Application` / app-of-apps + Kubernetes manifests) that
  deploys the SaaS app image onto the k3s cluster.
- Add a first **tenant-facing SaaS app** (frontend + backend) that lists jobs, submits a run, and
  shows results. It uses a **mock job backend** initially (no real GPU orchestration yet); the
  proposed production tech stack is recorded in design.md.
- **BREAKING**: none — all additions are new resources/files; existing Serverless job infra is
  untouched.

## Capabilities

### New Capabilities
- `saas-control-plane-infra`: Terraform for the `saas-server` VM, its service account, static IP,
  and cloud-init bootstrap of k3s + ArgoCD; MysteryBox secrets and IAM for GitHub and registry
  access.
- `gitops-delivery`: ArgoCD GitOps layout that syncs Kubernetes manifests from Git, sources the
  GitHub and registry credentials from MysteryBox, and deploys the SaaS app onto k3s.
- `saas-image-pipeline`: GitHub Actions workflow that builds and pushes the SaaS app image to the
  Nebius Registry, with a documented, reproducible registry-authentication method for CI.
- `saas-tenant-app`: the tenant-facing SaaS application (frontend + backend + optional storage) that
  submits jobs and returns results, backed by a mock orchestrator for this change.

### Modified Capabilities
<!-- None: no existing spec's requirements change. -->

## Impact

- **Infra**: new `saas.tf` (or additions to `main.tf`), `variables.tf`, `outputs.tf`, and a
  `cloud-init/` bootstrap under `sim2policy/infra/nebius/`. New Nebius resources: 1 CPU VM, 1 service
  account, static IP, MysteryBox secret(s), IAM permits. Small recurring cost (always-on `cpu-e2`
  `2vcpu-8gb`).
- **CI/CD**: new `.github/workflows/` pipeline and repo/organization secrets for Nebius Registry
  auth.
- **New app code**: a `saas/` (or `web/`) application tree — frontend, backend, Kubernetes manifests,
  ArgoCD `Application` definitions.
- **Security surface**: a publicly reachable server and stored long-lived credentials; threat model
  and least-privilege boundaries are defined in design.md and specs.
- **Docs**: README / infra README updates describing the control plane and CI auth.
