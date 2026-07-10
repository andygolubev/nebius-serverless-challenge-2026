output "saas_server_id" {
  value = nebius_compute_v1_instance.saas_server.id
}

output "saas_server_service_account_id" {
  value = nebius_iam_v1_service_account.saas_server.id
}

output "saas_github_secret_id" {
  description = "MysteryBox secret id holding the ArgoCD GitHub token."
  value       = nebius_mysterybox_v1_secret.saas_github_token.id
}

output "saas_ci_service_account_id" {
  description = "Service account used to issue the GitHub Actions CONTAINER_REGISTRY static token."
  value       = nebius_iam_v1_service_account.saas_ci.id
}
