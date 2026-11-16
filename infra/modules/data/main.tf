# rwc-content: the public lexicon, read by the API (docs/aws-architecture.md §3.1).
# Learner data (rwc-progress) and the review log are not built yet.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
}

variable "name" {
  type = string
}

variable "table_name" {
  type = string
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

# Key policy only delegates to IAM; roles get key access through their own policies.
data "aws_iam_policy_document" "content_key" {
  statement {
    sid       = "AccountAdministersKeyThroughIam"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_kms_key" "content" {
  description             = "${var.name} lexicon table"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.content_key.json
}

resource "aws_kms_alias" "content" {
  name          = "alias/${var.name}-content"
  target_key_id = aws_kms_key.content.key_id
}

resource "aws_dynamodb_table" "content" {
  name                        = var.table_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = true

  dynamic "attribute" {
    for_each = toset(["pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk"])

    content {
      name = attribute.value
      type = "S"
    }
  }

  # Browse by category. Created per the spec; the API reads from its in-memory cache today.
  global_secondary_index {
    name            = "GSI1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  # Review queue: lowest-confidence entries first, per verification status.
  global_secondary_index {
    name            = "GSI2"
    hash_key        = "gsi2pk"
    range_key       = "gsi2sk"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.content.arn
  }
}

output "table_name" {
  value = aws_dynamodb_table.content.name
}

output "table_arn" {
  value = aws_dynamodb_table.content.arn
}

output "kms_key_arn" {
  value = aws_kms_key.content.arn
}
