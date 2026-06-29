output "artifact_bucket" {
  value = nebius_storage_v1_bucket.artifacts.name
}

output "artifact_bucket_id" {
  value = nebius_storage_v1_bucket.artifacts.id
}

output "artifact_secret_selector" {
  description = "MysteryBox selector accepted by the Serverless AI --env-secret flag."
  value       = nebius_iam_v2_access_key.artifacts.status.secret_reference_id
}

output "registry_fqdn" {
  value = nebius_registry_v1_registry.sim2policy.status.registry_fqdn
}

output "registry_id" {
  value = nebius_registry_v1_registry.sim2policy.id
}

output "sb3_image" {
  value = "${nebius_registry_v1_registry.sim2policy.status.registry_fqdn}/${trimprefix(nebius_registry_v1_registry.sim2policy.id, "registry-")}/sim2policy:sb3"
}

output "mjx_image" {
  value = "${nebius_registry_v1_registry.sim2policy.status.registry_fqdn}/${trimprefix(nebius_registry_v1_registry.sim2policy.id, "registry-")}/sim2policy:mjx"
}
