# Nebius infrastructure with OpenTofu

This stack uses OpenTofu 1.12.3 and the Nebius provider 0.6.22. It creates a bounded artifact
bucket, container registry, and a least-privilege service-account access key delivered through
MysteryBox. Serverless AI jobs remain explicit workload submissions through `jobs/submit.sh`.

The remote-state bucket, state service account, access group/permit, and access key are bootstrap
resources. Create them with the Nebius CLI before `tofu init`; never commit their credentials.
The official recipe is https://docs.nebius.com/object-storage/store-terraform-state.

```bash
source ~/.config/sim2policy/tofu-backend.env
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
# Fill in the bucket, project, and tenant values.
export NEBIUS_IAM_TOKEN="$(nebius iam get-access-token)"
tofu init -backend-config=backend.hcl
tofu plan -out=sim2policy.tfplan
tofu apply sim2policy.tfplan
```

Use `tofu output -raw sb3_image`, `artifact_bucket`, `artifact_access_key_id`, and
`artifact_secret_selector` when building, pushing, and submitting jobs. The access key ID is
non-secret; the selector resolves only the secret access key and must be supplied with
`--env-secret`. The artifact bucket is capped at 50 GiB and aborts incomplete multipart uploads
after one day to bound accidental storage growth.

## SaaS control-plane server (add-saas-server)

`saas.tf` provisions an always-on `saas-server` CPU VM that self-bootstraps a single-node **k3s**
cluster and **ArgoCD** via `cloud-init/saas-server.yaml.tftpl`. ArgoCD GitOps-deploys the
tenant-facing SaaS app image (`saas/`, built by `.github/workflows/saas-image.yml`) from the
manifests in `deploy/`. The GitHub token (for ArgoCD repo access) is stored in **MysteryBox**;
cloud-init fetches it at boot using the VM service-account identity.

```bash
cp saas.tfvars.example saas.auto.tfvars   # fill in; keep out of Git
tofu plan  -out=saas.tfplan -var "github_token=$GITHUB_TOKEN"
tofu apply saas.tfplan
tofu output -raw saas_server_public_ip
```

**Network posture.** A `nebius_vpc_v1_security_group` allows inbound only 22 (SSH), 443 (HTTPS),
and 80 (ACME/redirect). The k3s API (6443) and ArgoCD UI are **not** public — manage the cluster
over an SSH tunnel (`ssh -L`, see `saas/README.md`). A host `ufw` firewall in cloud-init is
defense-in-depth. Narrow `saas_ssh_ingress_cidrs` to operator IPs.

**Domain and TLS.** The site is served at `https://sim-policy-trainer-challenge.info`. DNS is
managed manually at the registrar (not Terraform): an A record for
`sim-policy-trainer-challenge.info` must point at `tofu output -raw saas_server_public_ip`
(re-check after any re-provision, since the public IP can change). Certificates come from
Let's Encrypt via cert-manager, installed GitOps-style through ArgoCD
(`deploy/argocd/cert-manager-app.yaml` + issuers in `deploy/manifests/cert-manager/`); the
ACME HTTP-01 challenge uses the already-open port 80, so no firewall change is involved. To
change the domain, update the host in `deploy/manifests/saas/ingress.yaml` and the registrar's
A record.

**Registry auth for the server.** A real k3s boot test confirmed that containerd cannot exchange
the VM identity directly with Nebius Registry. Grant the VM service account `viewer` on the
registry, issue a `CONTAINER_REGISTRY` static key with `nebius iam static-key issue`, store its
token in MysteryBox under the key `token`, and set `saas_use_registry_pull_secret = true` plus
`saas_registry_pull_secret_id = "mbsec-..."`. Cloud-init reads that token and creates the
`dockerconfigjson` imagePullSecret with username `iam`.

**Registry auth for GitHub Actions.** Create a Nebius service account with `editor` on the registry,
issue a `CONTAINER_REGISTRY` static key, and set repo secrets `NEBIUS_REGISTRY` (FQDN plus registry
ID) and `NEBIUS_REGISTRY_TOKEN`. The workflow logs in as `iam` with
`docker login --password-stdin`. Alternative: install the Nebius CLI in CI and mint a short-lived
token with `nebius iam get-access-token`.

The stack creates the dedicated `sim2policy-saas-ci` service account and grants it registry-scoped
`editor` access. Issue its token with:

```bash
nebius iam static-key issue \
  --parent-id <project-id> \
  --account-service-account-id "$(tofu output -raw saas_ci_service_account_id)" \
  --service container_registry
```

**Rebuild / rollback.** All durable state is in Git (manifests) and S3 (artifacts), so the server is
disposable: `tofu destroy -target=nebius_compute_v1_instance.saas_server` and re-apply to rebuild,
or `tofu destroy` the saas-* resources to remove the control plane entirely without touching the
existing Serverless-job infra.

> The MysteryBox secret uses the state-saved `secret_version` field (token lands in the
> access-controlled S3 state backend, never in Git). Switch to the write-only
> `sensitive.secret_version.payload` field to keep it out of state on Terraform ≥ 1.11.

## Serverless job orchestration for the SaaS backend (nebius-job-orchestration)

The SaaS app's `nebius` orchestration backend submits tenant training runs as Serverless AI
jobs and reads their artifacts from the `sim2policy-artifacts` bucket. It needs a dedicated
service account plus a Kubernetes Secret assembled from MysteryBox values. None of this is in
Terraform yet; run the steps below with the Nebius CLI.

**1. Service account.** Create `sim2policy-saas-orchestrator` and grant it `editor` on the
project. `editor` is deliberately broad: Nebius currently requires at least `editor` to
create/cancel Serverless AI jobs and documents no job-scoped role (see the
[Serverless AI jobs quickstart](https://docs.nebius.com/serverless/quickstart/jobs)). Keep it
a dedicated account — do not reuse `sim2policy-saas-server` (registry viewer only) or
`sim2policy-saas-ci` (image pushes only) — and revisit when a narrower role ships.

```bash
nebius iam service-account create --parent-id project-e00wkbbppr00tab5fhhmz7 --name sim2policy-saas-orchestrator
nebius iam access-binding create \
  --resource-id project-e00wkbbppr00tab5fhhmz7 \
  --role editor \
  --subject-service-account-id <orchestrator-sa-id>
nebius iam auth-public-key generate \
  --service-account-id <orchestrator-sa-id> \
  --output ~/.config/sim2policy/saas-orchestrator-credentials.json
```

**2. MysteryBox.** Store the orchestrator credentials file in MysteryBox (same pattern as the
registry token). The artifact S3 credentials already exist: the non-secret access key ID is
`tofu output -raw artifact_access_key_id` and the secret access key is resolvable through the
MysteryBox selector `tofu output -raw artifact_secret_selector` — that selector is also what
the backend passes into each training job as the `AWS_SECRET_ACCESS_KEY` env-secret.

**3. Kubernetes Secret.** The deployment (`deploy/manifests/saas/deployment.yaml`) reads the
whole orchestration env contract from an optional Secret named `saas-nebius`; while it is
absent the app runs the built-in `mock` backend. Create it on the k3s server (over the SSH
tunnel) from MysteryBox-resolved values — never commit it, never put the values in a manifest:

Values below were verified with the CLI on 2026-07-11 (`tofu output` returns the same ones):

```bash
kubectl -n saas create secret generic saas-nebius \
  --from-literal=SAAS_ORCHESTRATION_BACKEND=nebius \
  --from-literal=NEBIUS_PROJECT_ID=project-e00wkbbppr00tab5fhhmz7 \
  --from-literal=NEBIUS_SUBNET_ID=vpcsubnet-e00re7tmw1apqd4pmm \
  --from-literal=SIM2POLICY_JOB_IMAGE=cr.eu-north1.nebius.cloud/e00gkhk5kcqp6fej6g/sim2policy:sb3-runtime \
  --from-literal=NEBIUS_S3_SECRET_SELECTOR=mbsec-e00k8grag4ncstap26/mbsecver-e00g8rehc7tsgxgahh \
  --from-literal=NEBIUS_REGISTRY_SECRET=mbsecver-e00v7zgpchp9apmy7m \
  --from-literal=AWS_ACCESS_KEY_ID=NAKIDE3R86YSA3ANIHIT \
  --from-literal=AWS_SECRET_ACCESS_KEY=<resolved from MysteryBox, e.g. via nebius mysterybox> \
  --from-literal=AWS_ENDPOINT_URL_S3=https://storage.eu-north1.nebius.cloud \
  --from-literal=AWS_DEFAULT_REGION=eu-north1 \
  --from-literal=SIM2POLICY_S3_BUCKET=sim2policy-artifacts \
  --from-literal=NEBIUS_CREDENTIALS_FILE=/var/run/secrets/nebius/credentials.json \
  --from-file=NEBIUS_CREDENTIALS_JSON="$HOME/.config/sim2policy/saas-orchestrator-credentials.json"
kubectl -n saas rollout restart deployment saas
```

> **Prerequisite — training image.** As of 2026-07-11 the `sim2policy-images` registry
> contains only `sim2policy-saas` (the control-plane app), not the training runtime.
> Build and push `sim2policy:sb3-runtime` from `sim2policy/Dockerfile` before submitting
> real jobs, or every submission will fail at image pull.

The deployment mounts the Secret's `NEBIUS_CREDENTIALS_JSON` key at
`/var/run/secrets/nebius/credentials.json`, which is where the
`NEBIUS_CREDENTIALS_FILE` literal above points the SDK. To roll back to the mock backend,
delete the Secret (or set `SAAS_ORCHESTRATION_BACKEND=mock` in it) and restart.
