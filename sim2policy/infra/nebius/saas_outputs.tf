output "saas_server_public_ip" {
  description = "Public IPv4 of the saas-server. SSH here; tunnel to reach k8s/ArgoCD."
  value       = one([for i in nebius_compute_v1_instance.saas_server.network_interfaces : i.public_ip_address.address])
}

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
