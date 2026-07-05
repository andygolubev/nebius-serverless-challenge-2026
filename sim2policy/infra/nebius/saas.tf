# Always-on SaaS control-plane server: a single-node k3s cluster running ArgoCD that
# GitOps-deploys the tenant-facing SaaS app image built from the Nebius Registry.
#
# Network posture: only SSH (22) and HTTPS (443) are exposed (80 for ACME/redirect).
# The k3s API (6443) and the ArgoCD UI stay private; operators manage the cluster over an
# SSH tunnel (`ssh -L`). See design.md Decision 6.

# --- Identity -----------------------------------------------------------------------------

resource "nebius_iam_v1_service_account" "saas_server" {
  parent_id = var.project_id
  name      = "${var.name_prefix}-saas-server"
}

# Least-privilege access group holding the saas-server SA. Permits attach to the group.
resource "nebius_iam_v1_group" "saas_server_access" {
  parent_id = var.tenant_id
  name      = "${var.name_prefix}-saas-server-access"
}

resource "nebius_iam_v1_group_membership" "saas_server" {
  parent_id = nebius_iam_v1_group.saas_server_access.id
  member_id = nebius_iam_v1_service_account.saas_server.id
}

# Node-identity image pull from the Sim2Policy registry (preferred over an imagePullSecret).
resource "nebius_iam_v1_access_permit" "saas_registry_pull" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = nebius_registry_v1_registry.sim2policy.id
  role        = "registry.puller"
}

# --- Secrets (MysteryBox) -----------------------------------------------------------------

# GitHub token ArgoCD uses to read the manifests repo. The value lives only in MysteryBox;
# cloud-init fetches it at boot using the VM service-account identity.
resource "nebius_mysterybox_v1_secret" "saas_github_token" {
  parent_id   = var.project_id
  name        = "${var.name_prefix}-saas-github-token"
  description = "GitHub token for ArgoCD repo access (add-saas-server)."

  # NOTE: with `secret_version` the token is written to Terraform state (kept in the
  # access-controlled S3 backend, never in Git). To keep it out of state entirely on
  # Terraform >= 1.11, switch to the write-only `sensitive.secret_version.payload` field.
  secret_version = {
    description = "Initial version."
    set_primary = true
    payload = [{
      key          = "token"
      string_value = var.github_token
    }]
  }
}

# Grant the VM service-account group read access to the GitHub-token secret payload.
resource "nebius_iam_v1_access_permit" "saas_github_secret_reader" {
  parent_id   = nebius_iam_v1_group.saas_server_access.id
  resource_id = nebius_mysterybox_v1_secret.saas_github_token.id
  role        = "mysterybox.secrets.payloadViewer"
}

# --- Network security group ----------------------------------------------------------------

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

# HTTP only for ACME challenge / redirect to HTTPS.
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

# SSH — narrow saas_ssh_ingress_cidrs to operator IPs. This is the only management path;
# kubectl/ArgoCD are reached by forwarding through this connection (ssh -L).
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

# Allow all egress (package installs, GitHub, registry, MysteryBox API).
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

# --- Compute instance ----------------------------------------------------------------------

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

  service_account_id = nebius_iam_v1_service_account.saas_server.id

  cloud_init_user_data = templatefile("${path.module}/cloud-init/saas-server.yaml.tftpl", {
    ssh_public_key       = var.saas_ssh_public_key
    github_secret_id     = nebius_mysterybox_v1_secret.saas_github_token.id
    argocd_repo_url      = var.saas_argocd_repo_url
    argocd_repo_path     = var.saas_argocd_repo_path
    argocd_repo_revision = var.saas_argocd_repo_revision
    use_registry_pull    = var.saas_use_registry_pull_secret
    registry_secret_id   = ""
  })
}
