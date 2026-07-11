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

**Issuing the static access key for the state backend.** The S3 state backend authenticates with a
static access key issued for the `sim2policy-tfstate` service account (`OpenTofu remote-state
access`). If the key is missing or expired (`tofu plan` fails with `403 AccessDenied` on the state
bucket), reissue it:

```bash
nebius iam v2 access-key create \
  --parent-id project-e00wkbbppr00tab5fhhmz7 \
  --account-service-account-id "$(nebius iam service-account get-by-name \
      --parent-id project-e00wkbbppr00tab5fhhmz7 \
      --name sim2policy-tfstate --format json | jq -r .metadata.id)" \
  --name tofu-state --description "OpenTofu remote-state access"
```

(Note: `nebius iam static-key issue` does not cover Object Storage — storage uses access keys.)
Store the returned `aws_access_key_id` and `secret` as `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in
`~/.config/sim2policy/tofu-backend.env` and `source` that file before every tofu command. Never
commit these credentials.

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
token as a version of the OpenTofu-created `sim2policy-saas-registry-pull` MysteryBox secret, and
set `saas_use_registry_pull_secret = true`. Cloud-init reads its versioned selector and creates the
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
attaches it to the SaaS VM. The pod mounts the VM-managed metadata token file read-only and the
Nebius SDK uses its renewable file bearer; there is no long-lived orchestrator key. `editor` remains deliberately isolated to this
identity because Nebius has no job-scoped create/cancel role. Replace it when one is available.

The artifact access key and registry token already deliver their payloads through MysteryBox.
OpenTofu references their IDs and immutable version IDs; it does not create duplicate secrets or
read payload values. Configure the non-secret references in the gitignored `saas.auto.tfvars`:

```hcl
saas_artifact_secret_version_id      = "mbsecver-..."
saas_registry_pull_secret_id         = "mbsec-..."
saas_registry_pull_secret_version_id = "mbsecver-..."
```

The access-key resource supplies the artifact secret ID; the explicit version completes its
immutable selector. The artifact payload key is `secret`, paired with `artifact_access_key_id`.
The registry payload key is `token`. To rotate either value, add a new primary version directly in
MysteryBox, update only the corresponding version ID, and apply:

```bash
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
destroy the orchestrator identity. The legacy service account remains a registry viewer because the
existing static pull token was issued for it; it is no longer attached to the VM.

## Mailjet SMTP secret for SaaS login codes

OpenTofu creates the `sim2policy-saas-smtp` MysteryBox container, seeds a non-working template
version through write-only provider fields, and grants the SaaS VM identity payload-viewer access
only to that secret. The template contains these exact keys:

```text
SAAS_SMTP_HOST
SAAS_SMTP_PORT
SAAS_SMTP_USER
SAAS_SMTP_PASSWORD
SAAS_SMTP_FROM
SAAS_SMTP_TLS_MODE
SAAS_SMTP_TIMEOUT_SECONDS
```

Never put a real Mailjet API Key or Secret Key in `.tf`, `.tfvars`, a plan, shell history, Git, or
this log. After the container exists, open it in the Nebius Console, create a new immutable version
from the template, replace `SAAS_SMTP_USER` with the Mailjet API Key and `SAAS_SMTP_PASSWORD` with
the Mailjet Secret Key, keep the other five values unchanged, and make the new version primary.
Record only its non-secret version ID in the gitignored `terraform.tfvars` (do not use the tracked
`saas.auto.tfvars`):

```hcl
saas_smtp_secret_version_id = "mbsecver-..."
```

Plan and apply that selector change, then install/reconcile the root-owned unit on an existing
server or let cloud-init do so on a rebuild:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now saas-smtp-sync.service
sudo systemctl --no-pager --full status saas-smtp-sync.service
sudo kubectl -n saas get secret saas-smtp -o json | jq -r '.data | keys[]'
```

The sync script requires exactly the seven allowlisted, non-empty keys and logs only key counts and
object names. It pins the configured MysteryBox version rather than following `primary`
implicitly. For rotation, create another MysteryBox version, update only
`saas_smtp_secret_version_id`, apply, restart the unit, restart the SaaS Deployment, verify bounded
delivery, and only then revoke the previous Mailjet Secret Key/version. To roll back, restore the
previous version ID, apply, rerun the unit, and restart the Deployment. Do not decode the Kubernetes
Secret or use `kubectl describe` during verification.

`.github/workflows/sb3-runtime-image.yml` builds the Dockerfile's `sb3` target on `sim2policy/**`
changes. It uses the existing `sim2policy-saas-ci` account through repository secrets
`NEBIUS_REGISTRY` and `NEBIUS_REGISTRY_TOKEN`, pushes the commit SHA first, then updates
`sim2policy:sb3-runtime` to the same image and records the digest. A failed immutable push never
updates the compatibility tag.
