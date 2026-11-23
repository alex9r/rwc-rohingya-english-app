# One-time setup, applied by the account owner with their own credentials.
# Creates the Terraform state bucket and lets GitHub Actions sign in with OIDC.
# This root keeps its own state locally (bootstrap/terraform.tfstate); back it up.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "rwc"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

variable "region" {
  description = "AWS region. ca-central-1 keeps data in Canada (spec §1)."
  type        = string
  default     = "ca-central-1"
}

# ------------------------------------------------------------ state bucket

resource "aws_s3_bucket" "state" {
  #checkov:skip=CKV_AWS_144:Cross-region replication of Terraform state isn't needed; versioning covers recovery.
  #checkov:skip=CKV_AWS_18:Access logging for the state bucket is out of scope for now.
  #checkov:skip=CKV2_AWS_62:No event notifications needed on the state bucket.
  bucket = "rwc-tfstate-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "state_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_tls_only.json
}

# ------------------------------------------------------- GitHub OIDC login

# Lets GitHub Actions get short-lived AWS credentials; no access keys are stored in GitHub.
# AWS validates GitHub's certificate itself; the thumbprints are only required by the API.
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a3a8518e8759bf075b76b750d4f2df264fcd"]
}

output "state_bucket" {
  description = "Pass to `terraform init -backend-config=\"bucket=...\"` in envs/dev."
  value       = aws_s3_bucket.state.bucket
}

output "github_oidc_provider_arn" {
  description = "Set as github_oidc_provider_arn in envs/dev."
  value       = aws_iam_openid_connect_provider.github.arn
}
