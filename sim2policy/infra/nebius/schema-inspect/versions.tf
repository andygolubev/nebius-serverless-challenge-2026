terraform {
  required_version = "= 1.12.3"
  required_providers {
    nebius = {
      source  = "registry.terraform.io/nebius/nebius"
      version = "= 0.6.22"
    }
  }
}

provider "nebius" {}
