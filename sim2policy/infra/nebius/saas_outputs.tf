output "saas_server_id" {
  value = nebius_compute_v1_instance.saas_server.id
}

output "saas_server_service_account_id" {
  description = "Deprecated unattached legacy SaaS server service account."
  value       = nebius_iam_v1_service_account.saas_server.id
}

output "saas_orchestrator_service_account_id" {
  description = "VM-attached identity used by the Nebius SDK through instance metadata."
  value       = nebius_iam_v1_service_account.saas_orchestrator.id
}

output "registry_pull_secret_selector" {
  description = "Versioned MysteryBox selector used for private runtime image pulls, or empty when disabled."
  value       = var.saas_use_registry_pull_secret && nebius_mysterybox_v1_secret.saas_registry_pull.primary_version_id != null ? "${nebius_mysterybox_v1_secret.saas_registry_pull.id}/${nebius_mysterybox_v1_secret.saas_registry_pull.primary_version_id}" : ""
}

output "saas_artifact_secret_selector" {
  description = "Versioned selector for the Terraform-managed SaaS artifact S3 secret."
  value       = nebius_mysterybox_v1_secret.saas_artifact_s3.primary_version_id != null ? "${nebius_mysterybox_v1_secret.saas_artifact_s3.id}/${nebius_mysterybox_v1_secret.saas_artifact_s3.primary_version_id}" : ""
}

output "saas_registry_secret_selector" {
  description = "Versioned selector for the Terraform-managed registry token."
  value       = nebius_mysterybox_v1_secret.saas_registry_pull.primary_version_id != null ? "${nebius_mysterybox_v1_secret.saas_registry_pull.id}/${nebius_mysterybox_v1_secret.saas_registry_pull.primary_version_id}" : ""
}

output "saas_artifact_secret_id" {
  description = "MysteryBox container whose versions are managed directly in Nebius Cloud."
  value       = nebius_mysterybox_v1_secret.saas_artifact_s3.id
}

output "saas_registry_secret_id" {
  description = "MysteryBox container whose versions are managed directly in Nebius Cloud."
  value       = nebius_mysterybox_v1_secret.saas_registry_pull.id
}

output "saas_nebius_contract" {
  description = "Selector-only and non-secret source contract reconciled into the saas-nebius Kubernetes Secret."
  value = {
    SAAS_ORCHESTRATION_BACKEND = "nebius"
    NEBIUS_PROJECT_ID          = var.project_id
    NEBIUS_SUBNET_ID           = var.saas_subnet_id
    SIM2POLICY_JOB_IMAGE       = "${nebius_registry_v1_registry.sim2policy.status.registry_fqdn}/${trimprefix(nebius_registry_v1_registry.sim2policy.id, "registry-")}/sim2policy:sb3-runtime"
    NEBIUS_S3_SECRET_SELECTOR  = nebius_mysterybox_v1_secret.saas_artifact_s3.primary_version_id != null ? "${nebius_mysterybox_v1_secret.saas_artifact_s3.id}/${nebius_mysterybox_v1_secret.saas_artifact_s3.primary_version_id}" : ""
    NEBIUS_REGISTRY_SECRET     = var.saas_use_registry_pull_secret && nebius_mysterybox_v1_secret.saas_registry_pull.primary_version_id != null ? nebius_mysterybox_v1_secret.saas_registry_pull.primary_version_id : ""
    AWS_ACCESS_KEY_ID          = nebius_iam_v2_access_key.artifacts.status.aws_access_key_id
    AWS_ENDPOINT_URL_S3        = "https://storage.eu-north1.nebius.cloud"
    AWS_DEFAULT_REGION         = "eu-north1"
    SIM2POLICY_S3_BUCKET       = nebius_storage_v1_bucket.artifacts.name
  }
}

output "saas_github_secret_id" {
  description = "MysteryBox secret id holding the ArgoCD GitHub token."
  value       = nebius_mysterybox_v1_secret.saas_github_token.id
}

output "saas_ci_service_account_id" {
  description = "Service account used to issue the GitHub Actions CONTAINER_REGISTRY static token."
  value       = nebius_iam_v1_service_account.saas_ci.id
}
