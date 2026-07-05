## 1. Terraform: saas-server VM

- [x] 1.1 Add `saas.tf` in `sim2policy/infra/nebius/` with a `nebius_compute_v1_instance` `saas-server` (static public IP, boot disk from `ubuntu24.04-driverless`), based on the provided snippet
- [x] 1.2 Parameterize into `saas_variables.tf`: `saas_subnet_id`, `saas_network_id`, `saas_platform` (default `cpu-e2`), `saas_preset` (default `2vcpu-8gb`), `saas_ssh_public_key`
- [x] 1.3 Fix the cloud-init user-data YAML (the `EOT`/`ssh_authorized_keys` indentation bug) and move it into `cloud-init/saas-server.yaml.tftpl` rendered via `templatefile()`
- [x] 1.4 Add output `saas_server_public_ip` (in `saas_outputs.tf`)
- [x] 1.5 Restrict inbound to SSH (22) + HTTPS (443) (and 80 for ACME/redirect) via `nebius_vpc_v1_security_group`/`_security_rule` on the instance NIC; add a host `ufw` firewall in cloud-init as defense-in-depth
- [x] 1.6 k3s API (6443) and ArgoCD kept private (k3s `--tls-san localhost`, ArgoCD ClusterIP; no public LB/ingress); `ssh -L` tunnel workflow documented in `saas/README.md` and infra README
- [ ] 1.7 `tofu plan` clean against a real project/tenant/subnet — PENDING (needs your Nebius state backend creds; `tofu validate` passes locally with only the documented write-only warning)

## 2. Terraform: credentials and IAM

- [x] 2.1 Create a MysteryBox secret for the GitHub token (from sensitive `github_token` var; no plaintext in Git)
- [x] 2.2 Grant the saas-server SA `registry.puller` via an access group (node-identity image pull) — VERIFY node-identity pull works before enabling the secret fallback (operational, at apply time)
- [ ] 2.3 Registry pull-credential fallback — scaffolded only: `saas_use_registry_pull_secret` var + cloud-init `dockerconfigjson` branch exist; the MysteryBox registry-credential resource is intentionally not created (default path is IAM). Implement if node-identity pull proves insufficient.
- [x] 2.4 Grant the SA group `mysterybox.secrets.payloadViewer` on the GitHub-token secret; no broad admin roles attached

## 3. Cloud-init: k3s + ArgoCD bootstrap

- [x] 3.1 cloud-init installs k3s and waits until `kubectl get nodes` reports Ready
- [x] 3.2 Installs ArgoCD into `argocd` via declarative `kubectl apply`; idempotent; logs to `/var/log/saas-bootstrap.log`
- [x] 3.3 Reads MysteryBox secrets at boot and materializes them as Kubernetes Secrets (ArgoCD repo credential; `dockerconfigjson` imagePullSecret only when the fallback is enabled)
- [x] 3.4 Applies the root app-of-apps ArgoCD `Application` pointing at `deploy/argocd`
- [ ] 3.5 `cloud-init schema` validation + boot-test on the VM — PENDING (needs the running VM). NOTE: confirm the exact `nebius mysterybox` CLI verb used to fetch the secret payload.

## 4. GitOps manifests

- [x] 4.1 Manifests live in this repo under `deploy/`; GitHub token scoped to this repo
- [x] 4.2 Root `Application` (app-of-apps, in cloud-init) + child `saas` `Application` (`deploy/argocd/saas-app.yaml`)
- [x] 4.3 Kubernetes manifests: `Deployment` (kustomize image mapping + optional imagePullSecret), `Service`, Traefik `Ingress` on 443
- [x] 4.4 Readiness + liveness probes on `/health`
- [ ] 4.5 Verify ArgoCD syncs and self-heals a manual edit — PENDING (needs the cluster)

## 5. GitHub Actions image pipeline

- [x] 5.1 `.github/workflows/saas-image.yml` builds the image on push to `main` and on `v*` tags
- [x] 5.2 Nebius Registry login via `docker login --password-stdin` from GH secrets (README documents both the key-based and `nebius iam get-access-token` methods)
- [x] 5.3 Tags with the 12-char commit SHA (immutable) plus a moving ref tag; pushes both
- [x] 5.4 Publish gated on the build step; credentials passed via stdin/secrets, never echoed
- [x] 5.5 Required GH Actions secrets and the auth method documented in the infra README

## 6. SaaS app: backend (FastAPI)

- [x] 6.1 FastAPI + Uvicorn backend with `/health` (smoke-tested)
- [x] 6.2 Job API: `POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/artifacts`
- [x] 6.3 Pluggable orchestration interface with a `mock` backend driving the full lifecycle and writing placeholder artifacts (in-memory for the mock stage; swaps to the S3 run tree for a real backend)
- [x] 6.4 Tenant scoping via `X-Tenant-Id` (other-tenant access returns 404 — verified)
- [x] 6.5 Dockerfile (multi-stage) for the app image

## 7. SaaS app: frontend (React + Vite + TS)

- [x] 7.1 React + Vite + TypeScript app with a job submit form and jobs list (inline styles; Tailwind optional follow-up)
- [x] 7.2 UI wired to the job API (submit, poll status every 1.5s, link to artifacts)
- [x] 7.3 Frontend builds to `backend/static` and is served by the backend in a single image

## 8. Wire-up, docs, and verification

- [ ] 8.1 `tofu apply`; verify SSH, k3s Ready, ArgoCD healthy — PENDING (needs your Nebius account)
- [ ] 8.2 Trigger CI; confirm image pushed and ArgoCD deploys it — PENDING
- [ ] 8.3 Hit `/health` through the ingress on the public IP; run the mock lifecycle end to end on-cluster — PENDING (lifecycle already verified locally)
- [ ] 8.3a Port-scan the public IP to confirm only 22/443 (and 80) open and k8s/ArgoCD unreachable except via the SSH tunnel — PENDING
- [x] 8.4 Updated infra README (control-plane architecture, CI auth, rebuild/rollback) and `saas/README.md`; open questions remain in design.md
