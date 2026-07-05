## 1. Terraform: saas-server VM

- [ ] 1.1 Add `saas.tf` in `sim2policy/infra/nebius/` with a `nebius_compute_v1_instance` `saas-server` (static public IP, boot disk from `ubuntu24.04-driverless`), based on the provided snippet
- [ ] 1.2 Parameterize into `variables.tf`: `saas_subnet_id`, `saas_platform` (default `cpu-e2`), `saas_preset` (default `2vcpu-8gb`), `saas_ssh_public_key`, `saas_service_account_id`
- [ ] 1.3 Fix the cloud-init user-data YAML (the `EOT`/`ssh_authorized_keys` indentation bug) and move it into `cloud-init/saas-server.yaml.tftpl` rendered via `templatefile()`
- [ ] 1.4 Add output `saas_server_public_ip` to `outputs.tf`
- [ ] 1.5 Restrict inbound network access to SSH (22) + HTTPS (443) (and 80 for ACME/redirect) via the Nebius security-group/allowlist on the instance NIC; add a host firewall (ufw/nftables) in cloud-init as defense-in-depth
- [ ] 1.6 Ensure the k3s API (6443) and ArgoCD server are bound to loopback/private only (install k3s without public API exposure; ArgoCD without a public LoadBalancer/ingress) and document the `ssh -L` tunnel workflow for kubectl/ArgoCD
- [ ] 1.7 `tofu validate` and `tofu plan` clean against a real project/tenant/subnet (no apply yet)

## 2. Terraform: credentials and IAM

- [ ] 2.1 Create a MysteryBox secret for the GitHub token (sensitive var or external ref; no plaintext in Git)
- [ ] 2.2 Grant the `saas-server` service account registry-pull (`registry.puller`-equivalent) role; verify whether node-identity pull works before adding a registry secret
- [ ] 2.3 If node-identity pull is insufficient, create a MysteryBox Nebius Registry pull credential and grant the service account secret-read
- [ ] 2.4 Grant the `saas-server` service account read access to the MysteryBox secrets it must consume; confirm no broad admin roles are attached

## 3. Cloud-init: k3s + ArgoCD bootstrap

- [ ] 3.1 In the cloud-init template, install k3s and wait until `kubectl get nodes` reports Ready
- [ ] 3.2 Install ArgoCD into an `argocd` namespace via declarative `kubectl apply`; make the step idempotent and log to a known path
- [ ] 3.3 On boot, read MysteryBox secrets and materialize them as Kubernetes Secrets (ArgoCD repo credential for the GitHub token; `dockerconfigjson` imagePullSecret only if the IAM pull path fails)
- [ ] 3.4 Apply the root app-of-apps ArgoCD `Application` pointing at the manifests repo/dir
- [ ] 3.5 Validate the user-data with `cloud-init schema` and boot-test on the VM

## 4. GitOps manifests

- [ ] 4.1 Decide manifests location (this repo `deploy/` vs separate repo) and scope the GitHub token accordingly
- [ ] 4.2 Add the root ArgoCD `Application` (app-of-apps) and the SaaS app child `Application`
- [ ] 4.3 Add Kubernetes manifests for the SaaS app: `Deployment` (referencing the registry image + imagePullSecret when needed), `Service`, and ingress on the public IP
- [ ] 4.4 Add a health/liveness/readiness probe on the app's health endpoint
- [ ] 4.5 Verify ArgoCD syncs the app and reconciles a manual cluster edit (self-heal)

## 5. GitHub Actions image pipeline

- [ ] 5.1 Add `.github/workflows/saas-image.yml` building the SaaS image on merge to default branch and on tags
- [ ] 5.2 Implement Nebius Registry login using a service-account credential from GH Actions secrets via `--password-stdin` (document both the key-based and `nebius iam get-access-token` methods)
- [ ] 5.3 Tag images with the commit SHA (immutable) plus a moving tag; push to the Nebius Registry
- [ ] 5.4 Gate publish on build/tests passing; confirm no credential values appear in logs
- [ ] 5.5 Document required GitHub Actions secrets and the auth method in the infra README

## 6. SaaS app: backend (FastAPI)

- [ ] 6.1 Scaffold the SaaS backend service (FastAPI + Uvicorn) with a `/health` endpoint
- [ ] 6.2 Implement job API: `POST /jobs` (submit), `GET /jobs/{id}` (status), `GET /jobs/{id}/artifacts` (results)
- [ ] 6.3 Implement a pluggable orchestration interface with a `mock` backend driving the full lifecycle and writing placeholder artifacts to the S3 run tree
- [ ] 6.4 Enforce tenant scoping so a tenant reads/acts only on its own jobs
- [ ] 6.5 Add a Dockerfile for the backend image

## 7. SaaS app: frontend (React + Vite + TS)

- [ ] 7.1 Scaffold a React + Vite + TypeScript app (Tailwind) with a job submit form and a jobs list
- [ ] 7.2 Wire the UI to the backend job API (submit, poll status, view artifacts)
- [ ] 7.3 Build static assets and serve them (nginx sidecar or from the backend); include in the app image

## 8. Wire-up, docs, and verification

- [ ] 8.1 `tofu apply`; verify SSH, k3s Ready, and ArgoCD healthy on the VM
- [ ] 8.2 Trigger the CI pipeline; confirm an image is pushed and ArgoCD deploys it
- [ ] 8.3 Hit the app health endpoint through the ingress on the public IP; run the mock job lifecycle end to end
- [ ] 8.3a Port-scan the public IP to confirm only 22/443 (and 80) are open; confirm k8s API/ArgoCD are unreachable directly and manageable only via the SSH tunnel
- [ ] 8.4 Update README / infra README with the control-plane architecture, registry CI auth, rebuild/rollback, and open questions (OIDC, IAM pull role name, domain/TLS)
