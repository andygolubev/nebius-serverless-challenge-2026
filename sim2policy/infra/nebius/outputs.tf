output "artifact_bucket" {
  value = nebius_storage_v1_bucket.artifacts.name
}

output "artifact_bucket_id" {
  value = nebius_storage_v1_bucket.artifacts.id
}

output "artifact_secret_selector" {
  description = "MysteryBox selector containing the AWS secret access key for --env-secret."
  value       = "${nebius_iam_v2_access_key.artifacts.status.secret_reference_id}/${var.saas_artifact_secret_version_id}"
}

output "artifact_access_key_id" {
  description = "Non-secret AWS access key ID paired with artifact_secret_selector."
  value       = nebius_iam_v2_access_key.artifacts.status.aws_access_key_id
}

output "artifact_endpoint" {
  value = "https://storage.eu-north1.nebius.cloud"
}

output "artifact_region" {
  value = "eu-north1"
}

output "project_id" {
  value = var.project_id
}

output "saas_subnet_id" {
  value = var.saas_subnet_id
}

output "registry_fqdn" {
  value = nebius_registry_v1_registry.sim2policy.status.registry_fqdn
}

output "registry_id" {
  value = nebius_registry_v1_registry.sim2policy.id
}

output "sb3_image" {
  value = "${nebius_registry_v1_registry.sim2policy.status.registry_fqdn}/${trimprefix(nebius_registry_v1_registry.sim2policy.id, "registry-")}/sim2policy:${var.saas_sb3_image_tag}"
}

output "mjx_image" {
  value = "${nebius_registry_v1_registry.sim2policy.status.registry_fqdn}/${trimprefix(nebius_registry_v1_registry.sim2policy.id, "registry-")}/sim2policy:${var.saas_mjx_image_tag}"
}
