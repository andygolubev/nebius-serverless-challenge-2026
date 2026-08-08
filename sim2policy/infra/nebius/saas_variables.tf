variable "saas_subnet_id" {
  description = "Subnet the saas-server network interface attaches to."
  type        = string
}

variable "saas_network_id" {
  description = "VPC network that owns the saas-server security group (parent of the subnet)."
  type        = string
}

variable "saas_platform" {
  description = "Compute platform for the saas-server VM."
  type        = string
  default     = "cpu-e2"
}

variable "saas_preset" {
  description = "Compute preset for the saas-server VM."
  type        = string
  default     = "2vcpu-8gb"
}

variable "saas_boot_disk_size_bytes" {
  description = "Boot disk size for the saas-server VM."
  type        = number
  default     = 107374182400
}

variable "saas_ssh_public_key" {
  description = "SSH public key authorized for the saas-server sudo user."
  type        = string
}

variable "saas_ssh_ingress_cidrs" {
  description = "Source CIDRs allowed to reach SSH (22). Narrow this to operator IPs; k8s/ArgoCD are reached only through this SSH tunnel."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "saas_argocd_repo_url" {
  description = "Git repository ArgoCD syncs the root app-of-apps from."
  type        = string
}

variable "saas_argocd_repo_path" {
  description = "Path within the repo that holds the ArgoCD root Application manifest."
  type        = string
  default     = "deploy/argocd"
}

variable "saas_argocd_repo_revision" {
  description = "Git revision ArgoCD tracks."
  type        = string
  default     = "main"
}

variable "saas_use_registry_pull_secret" {
  description = "Enable only if VM service-account registry pull is insufficient."
  type        = bool
  default     = false
}

variable "saas_artifact_secret_version_id" {
  description = "Existing immutable MysteryBox version containing the artifact S3 secret access key."
  type        = string
}

variable "saas_smtp_secret_version_id" {
  description = "Pinned MysteryBox version containing the seven-key Mailjet SMTP contract; empty until the operator creates the real version."
  type        = string
  default     = ""
}

variable "saas_job_registry_secret_version_id" {
  description = "Pinned MysteryBox version holding REGISTRY_USERNAME/REGISTRY_PASSWORD for Serverless AI job image pulls; empty until the operator creates the real version."
  type        = string
  default     = ""
}

variable "saas_mjx_image_tag" {
  description = "Immutable MJX runtime tag accepted for production GPU jobs."
  type        = string
  default     = "mjx-ce4ad5a0a2e957020f74dd208f71eb21135f4a9c"

  validation {
    condition     = can(regex("^mjx-[0-9a-f]{40}$", var.saas_mjx_image_tag))
    error_message = "saas_mjx_image_tag must be an immutable mjx-<40-character git SHA> tag."
  }
}

variable "saas_sb3_image_tag" {
  description = "Immutable SB3 runtime tag accepted for production gallery and custom-robot jobs."
  type        = string
  default     = "sb3-d905e49136ee1aad3b214574e394c1024521ebb6"

  validation {
    condition     = can(regex("^sb3-[0-9a-f]{40}$", var.saas_sb3_image_tag))
    error_message = "saas_sb3_image_tag must be an immutable sb3-<40-character git SHA> tag."
  }
}

variable "saas_registry_pull_secret_id" {
  description = "Existing MysteryBox secret containing the CONTAINER_REGISTRY token under key `token`."
  type        = string
  default     = ""

  validation {
    condition     = !var.saas_use_registry_pull_secret || var.saas_registry_pull_secret_id != ""
    error_message = "saas_registry_pull_secret_id is required when registry secret use is enabled."
  }
}

variable "saas_registry_pull_secret_version_id" {
  description = "Existing immutable MysteryBox version containing the CONTAINER_REGISTRY token."
  type        = string
  default     = ""

  validation {
    condition     = !var.saas_use_registry_pull_secret || var.saas_registry_pull_secret_version_id != ""
    error_message = "saas_registry_pull_secret_version_id is required when registry secret use is enabled."
  }
}
