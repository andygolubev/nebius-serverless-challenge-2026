resource "nebius_registry_v1_registry" "sim2policy" {
  parent_id   = var.project_id
  name        = "${var.name_prefix}-images"
  description = "Backend-isolated Sim2Policy SB3 and MJX images"
}

resource "nebius_storage_v1_bucket" "artifacts" {
  parent_id = var.project_id
  name      = "${var.name_prefix}-artifacts"

  default_storage_class = "STANDARD"
  force_storage_class   = true
  max_size_bytes        = var.artifact_bucket_max_bytes
  object_audit_logging  = "MUTATE_ONLY"
  versioning_policy     = "ENABLED"

  lifecycle_configuration = {
    rules = [{
      id                                = "abort-incomplete-uploads"
      status                            = "ENABLED"
      filter                            = { prefix = "" }
      abort_incomplete_multipart_upload = { days_after_initiation = 1 }
    }]
  }
}

resource "nebius_iam_v1_service_account" "artifacts" {
  parent_id = var.project_id
  name      = "${var.name_prefix}-artifacts"
}

resource "nebius_iam_v1_group" "artifact_object_editors" {
  parent_id = var.tenant_id
  name      = "${var.name_prefix}-artifact-object-editors"
}

resource "nebius_iam_v1_group_membership" "artifacts" {
  parent_id = nebius_iam_v1_group.artifact_object_editors.id
  member_id = nebius_iam_v1_service_account.artifacts.id
}

resource "nebius_iam_v1_access_permit" "artifacts" {
  parent_id   = nebius_iam_v1_group.artifact_object_editors.id
  resource_id = nebius_storage_v1_bucket.artifacts.id
  role        = "storage.object-editor"
}

resource "nebius_iam_v2_access_key" "artifacts" {
  parent_id = var.project_id
  name      = "${var.name_prefix}-artifacts"
  account = {
    service_account = { id = nebius_iam_v1_service_account.artifacts.id }
  }
  description          = "S3-compatible credentials for Sim2Policy Serverless AI jobs"
  secret_delivery_mode = "MYSTERY_BOX"
}
