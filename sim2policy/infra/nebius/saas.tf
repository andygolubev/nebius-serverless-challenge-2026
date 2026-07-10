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
# private key or credentials file exists. `editor` is the narrowest role that
# currently permits Serverless AI job create/cancel; replace it when Nebius
# publishes a job-scoped role.
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
  role        = "editor"
}

resource "nebius_iam_v1_group" "saas_server_access" {
  parent_id = var.tenant_id
  name      = "${var.name_prefix}-saas-server-access"
}

resource "nebius_iam_v1_group_membership" "saas_server" {
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

# The provider does not expose Container Registry static keys. Issue a
# CONTAINER_REGISTRY static key with the CLI, store its token in MysteryBox,
# and provide only that non-secret MysteryBox selector to this stack.
resource "nebius_iam_v1_access_permit" "saas_registry_pull_secret_reader" {
  count       = var.saas_use_registry_pull_secret && var.saas_registry_pull_secret_id != "" ? 1 : 0
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

  secret_version = {
    description = "Initial version."
    set_primary = true
    payload = [{
      key          = "token"
      string_value = var.github_token
    }]
  }
}

resource "nebius_iam_v1_access_permit" "saas_github_secret_reader" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = nebius_mysterybox_v1_secret.saas_github_token.id
  role        = "mysterybox.payload-viewer"
}

resource "nebius_iam_v1_access_permit" "saas_artifact_secret_reader" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = split("/", nebius_iam_v2_access_key.artifacts.status.secret_reference_id)[0]
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
    ssh_public_key       = var.saas_ssh_public_key
    github_secret_id     = nebius_mysterybox_v1_secret.saas_github_token.id
    argocd_repo_url      = var.saas_argocd_repo_url
    argocd_repo_path     = var.saas_argocd_repo_path
    argocd_repo_revision = var.saas_argocd_repo_revision
    use_registry_pull    = var.saas_use_registry_pull_secret
    registry_secret_id   = var.saas_registry_pull_secret_id
    registry_secret_selector = var.saas_use_registry_pull_secret ? "${var.saas_registry_pull_secret_id}/${var.saas_registry_pull_secret_version_id}" : ""
    registry_secret_version_id = var.saas_use_registry_pull_secret ? var.saas_registry_pull_secret_version_id : ""
    registry_host        = nebius_registry_v1_registry.sim2policy.status.registry_fqdn
    project_id            = var.project_id
    subnet_id             = var.saas_subnet_id
    job_image             = "${nebius_registry_v1_registry.sim2policy.status.registry_fqdn}/${trimprefix(nebius_registry_v1_registry.sim2policy.id, "registry-")}/sim2policy:sb3-runtime"
    artifact_selector     = nebius_iam_v2_access_key.artifacts.status.secret_reference_id
    artifact_access_key_id = nebius_iam_v2_access_key.artifacts.status.aws_access_key_id
    artifact_bucket       = nebius_storage_v1_bucket.artifacts.name
  })
}
