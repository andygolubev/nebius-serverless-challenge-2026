variable "project_id" {
  description = "Nebius project that owns Sim2Policy resources."
  type        = string
}

variable "tenant_id" {
  description = "Nebius tenant that owns the least-privilege artifact access group."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "sim2policy"
}

variable "artifact_bucket_max_bytes" {
  description = "Hard safety cap for generated checkpoints, logs, reports, and media."
  type        = number
  default     = 53687091200
}
