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

variable "github_token" {
  description = "GitHub token ArgoCD uses to read the manifests repo. Stored only in MysteryBox; keep out of Git."
  type        = string
  sensitive   = true
}

variable "saas_use_registry_pull_secret" {
  description = "Enable only if VM service-account registry pull is insufficient."
  type        = bool
  default     = false
}

variable "saas_artifact_secret_access_key" {
  description = "Secret half of the existing artifact S3 access key. Supplied only at apply time and written to MysteryBox through a write-only field."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "saas_artifact_secret_generation" {
  description = "Non-secret rotation generation for the write-only artifact payload; increment when changing the value."
  type        = string
  default     = "1"
}

variable "saas_registry_pull_token" {
  description = "CONTAINER_REGISTRY static-key token. Supplied only at apply time and written to MysteryBox through a write-only field."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "saas_registry_secret_generation" {
  description = "Non-secret rotation generation for the write-only registry payload; increment when changing the value."
  type        = string
  default     = "1"
}
