saas_subnet_id            = "vpcsubnet-e00re7tmw1apqd4pmm"
saas_network_id           = "vpcnetwork-e00gcst9b3y53vf9bq"
saas_platform             = "cpu-e2"
saas_preset               = "2vcpu-8gb"
saas_boot_disk_size_bytes = 107374182400

saas_ssh_public_key    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHvAUDb/hP3qw+GjXusgyn0sLSu3KkoxlRLLDVVMPCrH andy@mbp15"
saas_ssh_ingress_cidrs = ["147.235.195.89/32"]

saas_argocd_repo_url      = "https://github.com/andygolubev/nebius-serverless-challenge-2026.git"
saas_argocd_repo_path     = "deploy/argocd"
saas_argocd_repo_revision = "main"

saas_use_registry_pull_secret        = true
saas_artifact_secret_version_id      = "mbsecver-e00g8rehc7tsgxgahh"
saas_registry_pull_secret_id         = "mbsec-e00qz0hyrpcs12jsq9"
saas_registry_pull_secret_version_id = "mbsecver-e00v7zgpchp9apmy7m"
