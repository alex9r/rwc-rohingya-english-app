terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.6"
    }
  }

  # Partial configuration: the bucket comes from the bootstrap root at init time, e.g.
  #   terraform init -backend-config="bucket=rwc-tfstate-<account-id>"
  backend "s3" {
    key          = "envs/dev/terraform.tfstate"
    region       = "ca-central-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  # Same tag keys as the data stack, plus budget_line so hosting spend shows separately
  # in Cost Explorer (docs/aws-cost-estimate.md, "Tracking spend against the lines").
  default_tags {
    tags = {
      project     = "rwc-rohingya-english-app"
      environment = var.environment
      managed_by  = "terraform"
      budget_line = "hosting"
    }
  }
}
