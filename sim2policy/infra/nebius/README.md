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

The stack creates `sim2policy-saas-orchestrator`, grants that account project `editor`, and
attaches it to the SaaS VM. The Nebius SDK authenticates through instance metadata; there is no
credentials file or long-lived orchestrator key. `editor` remains deliberately isolated to this
identity because Nebius has no job-scoped create/cancel role. Replace it when one is available.

Apply with the gitignored remote backend and variables, then inspect the selector-only contract:

```bash
tofu init -reconfigure -backend-config=backend.hcl
tofu plan -out=saas-orchestration.tfplan
tofu apply saas-orchestration.tfplan
tofu output -json saas_nebius_contract | jq 'keys'
```

Cloud-init installs `saas-nebius-sync.service`. It uses the VM identity to resolve the versioned
artifact credential from MysteryBox and applies `saas-nebius` without placing secret values in Git,
OpenTofu inputs, command arguments, or operator shell history. Rerun it after selector rotation:

```bash
sudo systemctl restart saas-nebius-sync.service
sudo systemctl --no-pager --full status saas-nebius-sync.service
kubectl -n saas get secret saas-nebius -o json | jq -r '.data | keys[]'
```

The last command lists key names only. Do not decode values or use `kubectl describe`. For rollback,
set the backend to `mock` or delete `saas-nebius`, restart the deployment, and only then detach or
destroy the orchestrator identity. The old VM service account is retained but no longer attached.

`.github/workflows/sb3-runtime-image.yml` builds the Dockerfile's `sb3` target on `sim2policy/**`
changes. It uses the existing `sim2policy-saas-ci` account through repository secrets
`NEBIUS_REGISTRY` and `NEBIUS_REGISTRY_TOKEN`, pushes the commit SHA first, then updates
`sim2policy:sb3-runtime` to the same image and records the digest. A failed immutable push never
updates the compatibility tag.
