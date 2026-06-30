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
