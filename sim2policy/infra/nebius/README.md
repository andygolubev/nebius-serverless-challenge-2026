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

**Registry auth for the server.** The VM service account is granted `registry.puller` so k3s pulls
the app image by node identity — no imagePullSecret. Set `saas_use_registry_pull_secret = true`
only if node-identity pull is unavailable; cloud-init then wires a `dockerconfigjson` secret.

**Registry auth for GitHub Actions.** Create a Nebius service account with `registry.pusher` on the
registry plus an access key, and set repo secrets `NEBIUS_REGISTRY` (FQDN from
`tofu output -raw registry_fqdn`), `NEBIUS_SA_KEY_ID`, and `NEBIUS_SA_SECRET`. The workflow logs in
with `docker login --password-stdin` (no secret echoed). Alternative: install the Nebius CLI in CI
and `docker login <registry> -u iam --password-stdin` with `nebius iam get-access-token`.

**Rebuild / rollback.** All durable state is in Git (manifests) and S3 (artifacts), so the server is
disposable: `tofu destroy -target=nebius_compute_v1_instance.saas_server` and re-apply to rebuild,
or `tofu destroy` the saas-* resources to remove the control plane entirely without touching the
existing Serverless-job infra.

> The MysteryBox secret uses the state-saved `secret_version` field (token lands in the
> access-controlled S3 state backend, never in Git). Switch to the write-only
> `sensitive.secret_version.payload` field to keep it out of state on Terraform ≥ 1.11.
