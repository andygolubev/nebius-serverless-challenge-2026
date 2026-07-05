## Context

Sim2Policy already provisions a Nebius container registry, a versioned artifact bucket, and a
least-privilege artifact service account with MysteryBox-delivered S3 credentials
(`sim2policy/infra/nebius/main.tf`). Training runs today are launched by hand via `make cloud-train`
or the FastAPI demo (`src/sim2policy/api/`) whose orchestration boundary already refuses user code
and supports a `mock` backend. There is **no always-on server** and **no continuous delivery**: the
demo API is started manually and nothing keeps a tenant-facing site running or updated.

This change adds the missing control plane. The user has supplied a working Nebius `nebius_compute_v1_instance`
snippet for a `cpu-e2` / `2vcpu-8gb` `saas-server` with a static public IP, service account
`serviceaccount-e00xbhvmmwjyxxjm2x`, subnet `vpcsubnet-e00ka7ggch340z2eyj`, and an SSH key — this is
the starting point for the Terraform. The server must self-bootstrap k3s + ArgoCD, and ArgoCD must
deploy a SaaS app whose image is built by GitHub Actions and pushed to the Nebius Registry. Secrets
(GitHub token, registry pull credential) come from Nebius MysteryBox. The tenant app is mock-backed
for now.

Constraints: the user's global rule forbids committing/pushing Git changes — all artifacts are
proposed only. No secret values may land in Git. Existing Serverless job infra must not regress.

## Goals / Non-Goals

**Goals:**
- Terraform for a long-lived `saas-server` VM that bootstraps k3s + ArgoCD via cloud-init,
  parameterized (platform/preset/subnet/project) rather than hardcoded.
- A GitOps delivery path: ArgoCD app-of-apps syncing Kubernetes manifests, credentials sourced from
  MysteryBox, image pulled from the Nebius Registry.
- A GitHub Actions pipeline that builds and pushes the SaaS image to the Nebius Registry, with a
  documented, reproducible registry-auth method.
- A first tenant-facing SaaS app (frontend + backend) with a `mock` orchestration backend and a
  recommended production tech stack.

**Non-Goals:**
- Real multi-tenant GPU orchestration of custom environments/policies (a later change; the mock
  backend and the pluggable interface leave room for it).
- Production-grade multi-node HA, autoscaling, managed Kubernetes, or a managed database.
- Billing/quotas/authn hardening beyond basic tenant scoping.
- TLS/domain automation beyond a documented path (can start as HTTP/IP or self-signed).

## Decisions

### Decision 1: Single-node k3s on one CPU VM (not managed Kubernetes)
k3s on the provided `cpu-e2` VM is the lightest way to get a real, ArgoCD-drivable cluster for a
demo/SaaS control plane. **Alternatives:** Nebius Managed Kubernetes (more moving parts and cost for
a single-node need); plain `docker compose` + a systemd unit (no GitOps story, which is an explicit
requirement); Nebius Serverless Containers for the site itself (weaker fit for hosting a stateful
ArgoCD control loop). k3s keeps `kubectl`/ArgoCD semantics while staying on one cheap VM.

### Decision 2: cloud-init installs k3s, then bootstraps ArgoCD idempotently
cloud-init `runcmd` (or a `write_files` script invoked once) will: install k3s
(`curl -sfL https://get.k3s.io | sh -`), wait for the node to be Ready, `kubectl apply` the ArgoCD
install manifest into an `argocd` namespace, then `kubectl apply` a single **root `Application`**
(app-of-apps) pointing at the Git manifests repo. Idempotency comes from k3s's installer being
re-run-safe and from using declarative `kubectl apply`. Keeping the user-data YAML valid matters —
the provided snippet has an indentation bug (the closing `EOT` is indented under `ssh_authorized_keys`),
which must be fixed or cloud-init will silently mis-parse.
**Alternatives:** a config-management tool (Ansible pull) — heavier; baking a custom image with
Packer — slower iteration for a demo.

### Decision 3: Credentials via MysteryBox → Kubernetes Secret; prefer IAM for registry
Terraform creates MysteryBox secrets for (a) a **GitHub token** (repo read for ArgoCD) and (b) a
**Nebius Registry pull credential**. The bootstrap reads these on the VM (the `saas-server` service
account is granted secret-read) and materializes them as Kubernetes Secrets: the GitHub token as an
ArgoCD repo-credential secret; the registry credential as a `kubernetes.io/dockerconfigjson`
`imagePullSecret` referenced by the SaaS Deployment.
**Registry auth — prefer IAM, fall back to secret:** grant the `saas-server` service account the
`registry.puller`/artifact-registry viewer role on the registry so the node can pull *without* a
secret. Nebius nodes can obtain registry credentials from their service-account identity; if that
path works, **no `imagePullSecret` is needed** and the MysteryBox registry credential is skipped.
The `imagePullSecret` path is the documented fallback for when node-identity pull is unavailable.
**Alternatives:** External Secrets Operator wired to MysteryBox (cleaner long-term, but more
infrastructure than a single-node demo needs); committing a sealed secret (adds sealed-secrets
controller and key management).

### Decision 4: GitHub Actions authenticates to Nebius Registry via a service-account key
The pipeline logs in to the registry FQDN (from `tofu output registry_fqdn`) with `docker login`
using a **Nebius service-account access-key/secret stored as GitHub Actions secrets**, then builds
and pushes tagged with the commit SHA. **Recommended concrete method** (documented in the workflow
and infra README):

1. Create (or reuse) a Nebius service account with `registry.pusher` role on the registry, and an
   access key for it (Terraform can output the access key id; the secret goes to MysteryBox or is
   read once and stored as a GH secret — never committed).
2. In the repo, set GitHub Actions secrets, e.g. `NEBIUS_REGISTRY`, `NEBIUS_SA_KEY_ID`,
   `NEBIUS_SA_SECRET` (or a single `NEBIUS_IAM_TOKEN` minted in-workflow via the Nebius CLI).
3. Workflow step:
   ```yaml
   - name: Log in to Nebius Registry
     run: |
       echo "${{ secrets.NEBIUS_SA_SECRET }}" | \
         docker login "${{ secrets.NEBIUS_REGISTRY }}" \
           --username "${{ secrets.NEBIUS_SA_KEY_ID }}" --password-stdin
   ```
   Alternative (token-based): install the Nebius CLI, run
   `nebius iam get-access-token`, and `docker login <registry> -u iam --password-stdin` with that
   token. Use `--password-stdin` so the secret never appears in `ps`/logs; rely on GitHub's secret
   masking.
**Alternatives:** OIDC federation from GitHub to Nebius (best practice, no long-lived key) — preferred
later, but only if Nebius supports GitHub OIDC federation; a personal access token — not
service-scoped, rejected.

### Decision 5: SaaS tech stack (frontend + backend + storage)
Recommendation, chosen to reuse what the repo already has and minimize new languages:

- **Backend: Python + FastAPI.** The repo is already a Python/FastAPI project with a working
  orchestration boundary and `mock` backend (`src/sim2policy/api/`). The SaaS backend extends that
  pattern rather than introducing a new runtime. Uvicorn/Gunicorn in the container.
- **Frontend: React + Vite + TypeScript** (styled with Tailwind), served as static assets by an
  nginx sidecar/container or from the backend. Small, standard, easy to host on k3s.
- **API style:** REST/JSON (matches existing `/train`, `/runs/<id>`, `/runs/<id>/artifacts`).
- **Storage:** for the mock stage, **no database** — job state persists to the existing S3 artifact
  bucket (same durable run-tree layout the demo API already writes), keeping the app stateless and
  restart-safe. If relational state is later needed (tenants, quotas), add **PostgreSQL** via a
  single k3s StatefulSet or Nebius Managed PostgreSQL. **SQLite on a PVC** is an acceptable
  interim.
- **Object artifacts/media:** the Nebius S3 bucket already provisioned.
**Alternatives considered:** Node/Express backend (would fork the codebase into two languages);
Next.js full-stack (heavier, SSR unneeded for a dashboard); Go backend (fast/small but abandons the
existing Python orchestration code).

### Decision 6: Minimal ingress firewall; k8s/ArgoCD over SSH tunnel
The VM exposes only what tenants and the operator need: inbound **22 (SSH)** and **443 (HTTPS)** for
the SaaS app, plus **80** solely for ACME/HTTP→HTTPS redirect. Everything else — the k3s API server
(6443), the ArgoCD server, NodePorts, kubelet — is closed to the internet. This is enforced at the
Nebius network layer (security-group / allowlist on the instance's network interface); a host
firewall (`ufw`/nftables via cloud-init) is a defense-in-depth backup, not the primary control.
**Cluster administration is tunnel-only:** ArgoCD's service and the kube API stay on the private
network / loopback, and the operator reaches them with
`ssh -L 8080:localhost:<argocd-port> saas-server` (and `kubectl` via the k3s kubeconfig over a
forwarded 6443, or by running `kubectl` on the host through SSH). ArgoCD is therefore configured
**not** to expose a public LoadBalancer/ingress; only the tenant SaaS app gets an ingress on 443.
**Alternatives:** exposing ArgoCD behind auth on 443 (larger attack surface, another public endpoint
to harden — rejected for now); a VPN/bastion (heavier than needed for a single operator — SSH tunnel
is sufficient); Nebius IAP-style access if available (revisit later). Note the k3s installer must be
told not to expose the API publicly and ArgoCD installed without a public service.

### Decision 7: Terraform layout and parameterization
Add `saas.tf` (VM, service account or reuse of the provided one, static IP, MysteryBox secrets, IAM
permits, cloud-init from `templatefile()`), extend `variables.tf` (`saas_subnet_id`,
`saas_platform`, `saas_preset`, `saas_ssh_public_key`, `github_token` as a sensitive var or external
secret ref) and `outputs.tf` (`saas_server_public_ip`). Cloud-init lives in
`infra/nebius/cloud-init/saas-server.yaml.tftpl`. Registry/bucket resources are reused, not
duplicated.

## Risks / Trade-offs

- **Public server + stored long-lived credentials** → Least-privilege service account (secret-read +
  registry pull only), MysteryBox for secrets, firewall/security-group to expose only 80/443/22,
  SSH key-only. Prefer IAM node-identity pull to avoid storing a registry secret at all.
- **Single-node, single-VM = single point of failure / no HA** → Acceptable for a demo/early SaaS;
  state kept in durable S3 so the VM is rebuildable from Terraform + GitOps. Document rebuild.
- **cloud-init YAML fragility** (the provided snippet's `EOT` indentation bug) → Fix indentation,
  validate with `cloud-init schema`, and keep bootstrap in a `write_files` script that logs to a
  known path for debugging.
- **Long-lived GitHub Actions registry key** → Scope to `registry.pusher` on one registry, rotate,
  and migrate to OIDC federation when available.
- **ArgoCD bootstrapping into a just-created cluster (race)** → Bootstrap waits for node Ready and
  retries `kubectl apply`; ArgoCD self-heal converges afterward.
- **Cost of an always-on VM** → smallest `cpu-e2`/`2vcpu-8gb` preset; documented and parameterized so
  it can be stopped when idle.

## Migration Plan

1. Land Terraform (`saas.tf`, vars, cloud-init template) and `tofu plan` review; no secret values in
   Git. Store the GitHub token and (if used) registry credential in MysteryBox.
2. `tofu apply` to create the VM; verify SSH, k3s Ready, ArgoCD up.
3. Add the GitOps manifests repo/dir and the root ArgoCD `Application`; confirm sync.
4. Add the GitHub Actions workflow + repo secrets; verify an image builds and pushes to the registry
   and ArgoCD deploys it.
5. Ship the mock-backed SaaS app; verify health endpoint via the public IP and the job lifecycle.
6. **Rollback:** `tofu destroy` the `saas-server` (and its IP/SA/secrets) leaves all existing
   Serverless-job infra untouched; delete the workflow and GH secrets to stop CI.

## Open Questions

- Does Nebius support **GitHub OIDC federation** so CI can avoid a long-lived registry key? (If yes,
  prefer it over Decision 4's stored key.)
- Can the `saas-server` service account pull from the registry via **node identity alone** (IAM), or
  is the `imagePullSecret` fallback required? Confirm the exact `registry.puller`-equivalent role
  name in the Nebius provider.
- Should the GitOps manifests live in **this repo** (a `deploy/` dir) or a **separate manifests
  repo**? This changes the ArgoCD repo credential and the GitHub token scope.
- Domain/TLS: start on HTTP/IP, or provision a domain + cert-manager/Let's Encrypt now?
- Which auth for tenants in the app (API keys vs. OIDC/SSO) once beyond the mock?
