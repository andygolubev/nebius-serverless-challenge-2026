# Always-on SaaS control-plane server: a single-node k3s cluster running ArgoCD that
# GitOps-deploys the tenant-facing SaaS app image built from the Nebius Registry.
#
# Network posture: only SSH (22) and HTTPS (443) are exposed (80 for ACME/redirect).
# The k3s API (6443) and the ArgoCD UI stay private; operators manage the cluster over an
# SSH tunnel (`ssh -L`). See design.md Decision 6.

resource "nebius_iam_v1_service_account" "saas_server" {
  parent_id = var.project_id
  name      = "${var.name_prefix}-saas-server"
}

# Dedicated runtime identity for the SaaS backend. The VM-attached identity is
# discovered by the Nebius SDK through instance metadata, so no long-lived SDK
# private key or credentials file exists. Nebius Support requested project
# `admin` as a temporary workaround after project `editor` allowed job creation
# but left every service-account-created job stuck in PROVISIONING. A live A/B
# probe on 2026-07-12 confirmed that `admin` reaches STARTING in about one minute.
# Revert to `editor` when Nebius confirms the underlying provisioner fix.
resource "nebius_iam_v1_service_account" "saas_orchestrator" {
  parent_id   = var.project_id
  name        = "${var.name_prefix}-saas-orchestrator"
  description = "VM identity for SaaS Serverless AI job orchestration"
}

resource "nebius_iam_v1_group" "saas_orchestrators" {
  parent_id = var.tenant_id
  name      = "${var.name_prefix}-saas-orchestrators"
}

resource "nebius_iam_v1_group_membership" "saas_orchestrator_editor" {
  parent_id = nebius_iam_v1_group.saas_orchestrators.id
  member_id = nebius_iam_v1_service_account.saas_orchestrator.id
}

resource "nebius_iam_v1_access_permit" "saas_orchestrator_editor" {
  parent_id   = nebius_iam_v1_group.saas_orchestrators.id
  resource_id = var.project_id
  role        = "admin"
}

resource "nebius_iam_v1_group" "saas_server_access" {
  parent_id = var.tenant_id
  name      = "${var.name_prefix}-saas-server-access"
}

resource "nebius_iam_v1_group_membership" "saas_server" {
  parent_id = nebius_iam_v1_group.saas_server_access.id
  member_id = nebius_iam_v1_service_account.saas_server.id
}

# The VM identity needs the same runtime read permissions. Keep the legacy
# account in the group as well because the existing CONTAINER_REGISTRY static
# token was issued for it and remains the k3s image-pull credential.
resource "nebius_iam_v1_group_membership" "saas_orchestrator_runtime_access" {
  parent_id = nebius_iam_v1_group.saas_server_access.id
  member_id = nebius_iam_v1_service_account.saas_orchestrator.id
}

resource "nebius_iam_v1_access_permit" "saas_registry_pull" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = nebius_registry_v1_registry.sim2policy.id
  # Container Registry has no pull-only service-specific role. The general
  # viewer role grants registry/image view, list, and pull without push.
  role = "viewer"
}

# The provider does not expose Container Registry static keys. The token and
# its MysteryBox version already exist and are referenced by ID only.
resource "nebius_iam_v1_access_permit" "saas_registry_pull_secret_reader" {
  count       = var.saas_use_registry_pull_secret ? 1 : 0
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = var.saas_registry_pull_secret_id
  role        = "mysterybox.payload-viewer"
}

# Dedicated GitHub Actions identity. Registry `editor` is the narrowest current
# Nebius role that permits image pushes; it is scoped to this registry only.
resource "nebius_iam_v1_service_account" "saas_ci" {
  parent_id = var.project_id
  name      = "${var.name_prefix}-saas-ci"
}

resource "nebius_iam_v1_group" "saas_ci_registry_editors" {
  parent_id = var.tenant_id
  name      = "${var.name_prefix}-saas-ci-registry-editors"
}

resource "nebius_iam_v1_group_membership" "saas_ci" {
  parent_id = nebius_iam_v1_group.saas_ci_registry_editors.id
  member_id = nebius_iam_v1_service_account.saas_ci.id
}

resource "nebius_iam_v1_access_permit" "saas_ci_registry_editor" {
  parent_id   = nebius_iam_v1_group.saas_ci_registry_editors.id
  resource_id = nebius_registry_v1_registry.sim2policy.id
  role        = "editor"
}

resource "nebius_mysterybox_v1_secret" "saas_github_token" {
  parent_id   = var.project_id
  name        = "${var.name_prefix}-saas-github-token"
  description = "GitHub token for ArgoCD repo access (add-saas-server)."

  # Payload versions are managed directly in MysteryBox. The original version
  # predates this change and must never be replaced merely because its value is
  # intentionally absent from configuration/state.
  lifecycle {
    ignore_changes = [secret_version, sensitive]
  }
}

resource "nebius_iam_v1_access_permit" "saas_github_secret_reader" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = nebius_mysterybox_v1_secret.saas_github_token.id
  role        = "mysterybox.payload-viewer"
}

# Seed a write-only template version. The two credential placeholders must be
# replaced by creating a new MysteryBox version out of band; real Mailjet
# credentials must never be committed to configuration or OpenTofu state.
resource "nebius_mysterybox_v1_secret" "saas_smtp" {
  parent_id   = var.project_id
  name        = "${var.name_prefix}-saas-smtp"
  description = "Mailjet SMTP settings for SaaS email-code delivery."

  secret_version = {
    description = "Mailjet SMTP template; replace credential placeholders in a new version."
    set_primary = true
  }

  # Write-only provider fields: payload values are sent during creation but
  # omitted from state. Keep real credentials out of this block regardless.
  sensitive = {
    version = "smtp-template-v1"
    secret_version = {
      payload = [
        {
          key          = "SAAS_SMTP_HOST"
          string_value = "in-v3.mailjet.com"
        },
        {
          key          = "SAAS_SMTP_PORT"
          string_value = "587"
        },
        {
          key          = "SAAS_SMTP_USER"
          string_value = "REPLACE_WITH_MAILJET_API_KEY"
        },
        {
          key          = "SAAS_SMTP_PASSWORD"
          string_value = "REPLACE_WITH_MAILJET_SECRET_KEY"
        },
        {
          key          = "SAAS_SMTP_FROM"
          string_value = "Sim2Policy <login@sim-policy-trainer-challenge.info>"
        },
        {
          key          = "SAAS_SMTP_TLS_MODE"
          string_value = "starttls"
        },
        {
          key          = "SAAS_SMTP_TIMEOUT_SECONDS"
          string_value = "10"
        },
      ]
    }
  }

  lifecycle {
    ignore_changes = [secret_version, sensitive]
  }
}

# The group contains both the legacy server identity and the VM-attached SaaS
# orchestrator identity, so rebuilt and current servers can reconcile the SMTP
# payload without any project-wide MysteryBox permission.
resource "nebius_iam_v1_access_permit" "saas_smtp_secret_reader" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = nebius_mysterybox_v1_secret.saas_smtp.id
  role        = "mysterybox.payload-viewer"
}

resource "nebius_iam_v1_access_permit" "saas_artifact_secret_reader" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = split("/", nebius_iam_v2_access_key.artifacts.status.secret_reference_id)[0]
  role        = "mysterybox.payload-viewer"
}

# Serverless AI jobs require registry credentials as a MysteryBox payload with
# exactly the REGISTRY_USERNAME and REGISTRY_PASSWORD keys. The existing
# sim2policy-saas-registry-pull secret stores a single `token` key (the k3s
# imagePullSecret shape) and is rejected by the jobs API, so this dedicated
# secret carries the job-pull shape. Seed a write-only template version; the
# operator replaces the password placeholder with the registry token in a new
# version out of band (Nebius Console), never through configuration or state.
resource "nebius_mysterybox_v1_secret" "saas_job_registry" {
  parent_id   = var.project_id
  name        = "${var.name_prefix}-job-registry-creds"
  description = "Registry pull credentials for Serverless AI job image pulls."

  secret_version = {
    description = "Job registry template; replace REGISTRY_PASSWORD in a new version."
    set_primary = true
  }

  sensitive = {
    version = "job-registry-template-v1"
    secret_version = {
      payload = [
        {
          key          = "REGISTRY_USERNAME"
          string_value = "iam"
        },
        {
          key          = "REGISTRY_PASSWORD"
          string_value = "REPLACE_WITH_REGISTRY_TOKEN"
        },
      ]
    }
  }

  lifecycle {
    ignore_changes = [secret_version, sensitive]
  }
}

# The orchestrator identity creates jobs that reference this secret; the jobs
# service resolves the payload at image-pull time under that identity.
resource "nebius_iam_v1_access_permit" "saas_job_registry_secret_reader" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = nebius_mysterybox_v1_secret.saas_job_registry.id
  role        = "mysterybox.payload-viewer"
}

resource "nebius_vpc_v1_security_group" "saas_server" {
  parent_id  = var.project_id
  name       = "${var.name_prefix}-saas-server"
  network_id = var.saas_network_id
}

resource "nebius_vpc_v1_security_rule" "saas_allow_https" {
  parent_id = nebius_vpc_v1_security_group.saas_server.id
  name      = "allow-https"
  access    = "ALLOW"
  protocol  = "TCP"
  priority  = 100
  type      = "STATEFUL"

  ingress = {
    source_cidrs      = ["0.0.0.0/0"]
    destination_ports = [443]
  }
}

resource "nebius_vpc_v1_security_rule" "saas_allow_http" {
  parent_id = nebius_vpc_v1_security_group.saas_server.id
  name      = "allow-http-acme"
  access    = "ALLOW"
  protocol  = "TCP"
  priority  = 110
  type      = "STATEFUL"

  ingress = {
    source_cidrs      = ["0.0.0.0/0"]
    destination_ports = [80]
  }
}

resource "nebius_vpc_v1_security_rule" "saas_allow_ssh" {
  parent_id = nebius_vpc_v1_security_group.saas_server.id
  name      = "allow-ssh"
  access    = "ALLOW"
  protocol  = "TCP"
  priority  = 120
  type      = "STATEFUL"

  ingress = {
    source_cidrs      = var.saas_ssh_ingress_cidrs
    destination_ports = [22]
  }
}

resource "nebius_vpc_v1_security_rule" "saas_allow_egress" {
  parent_id = nebius_vpc_v1_security_group.saas_server.id
  name      = "allow-egress"
  access    = "ALLOW"
  protocol  = "ANY"
  priority  = 200
  type      = "STATEFUL"

  egress = {
    destination_cidrs = ["0.0.0.0/0"]
  }
}

resource "nebius_compute_v1_instance" "saas_server" {
  parent_id = var.project_id
  name      = "${var.name_prefix}-saas-server"

  resources = {
    platform = var.saas_platform
    preset   = var.saas_preset
  }

  boot_disk = {
    attach_mode = "READ_WRITE"
    managed_disk = {
      name = "${var.name_prefix}-saas-server-boot-disk"
      spec = {
        type             = "NETWORK_SSD"
        block_size_bytes = 4096
        size_bytes       = var.saas_boot_disk_size_bytes
        source_image_family = {
          image_family = "ubuntu24.04-driverless"
        }
      }
    }
  }

  network_interfaces = [{
    name       = "eth0"
    subnet_id  = var.saas_subnet_id
    ip_address = {}
    public_ip_address = {
      static = true
    }
    security_groups = [{
      id = nebius_vpc_v1_security_group.saas_server.id
    }]
  }]

  service_account_id = nebius_iam_v1_service_account.saas_orchestrator.id

  cloud_init_user_data = templatefile("${path.module}/cloud-init/saas-server.yaml.tftpl", {
    ssh_public_key             = var.saas_ssh_public_key
    github_secret_id           = nebius_mysterybox_v1_secret.saas_github_token.id
    argocd_repo_url            = var.saas_argocd_repo_url
    argocd_repo_path           = var.saas_argocd_repo_path
    argocd_repo_revision       = var.saas_argocd_repo_revision
    use_registry_pull          = var.saas_use_registry_pull_secret
    registry_secret_id         = var.saas_registry_pull_secret_id
    registry_secret_selector   = var.saas_use_registry_pull_secret ? "${var.saas_registry_pull_secret_id}/${var.saas_registry_pull_secret_version_id}" : ""
    registry_secret_version_id = var.saas_use_registry_pull_secret ? var.saas_registry_pull_secret_version_id : ""
    registry_host              = nebius_registry_v1_registry.sim2policy.status.registry_fqdn
    project_id                 = var.project_id
    subnet_id                  = var.saas_subnet_id
    job_image                  = "${nebius_registry_v1_registry.sim2policy.status.registry_fqdn}/${trimprefix(nebius_registry_v1_registry.sim2policy.id, "registry-")}/sim2policy:sb3-runtime"
    artifact_selector          = "${nebius_iam_v2_access_key.artifacts.status.secret_reference_id}/${var.saas_artifact_secret_version_id}"
    artifact_access_key_id     = nebius_iam_v2_access_key.artifacts.status.aws_access_key_id
    artifact_bucket            = nebius_storage_v1_bucket.artifacts.name
    smtp_secret_selector       = var.saas_smtp_secret_version_id != "" ? "${nebius_mysterybox_v1_secret.saas_smtp.id}/${var.saas_smtp_secret_version_id}" : ""
  })
}
