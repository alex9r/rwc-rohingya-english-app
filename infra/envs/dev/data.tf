# The data stack (infra/*.tf, applied first from infra/) owns the tables, buckets, KMS
# keys and the data-access policies. This stack only looks them up, by the names the
# data stack gives them, and never creates or changes them.

locals {
  data_keys = toset(["content", "learner-data", "learner-audio"])
}

data "aws_dynamodb_table" "content" {
  name = "rwc-${var.environment}-content"
}

data "aws_kms_alias" "data" {
  for_each = local.data_keys
  name     = "alias/rwc-${var.environment}-${each.key}"
}

# What the API may touch (content read, learner progress, recording uploads), as the
# data stack decided. Attached to the Lambda role unchanged (modules/iam).
data "aws_iam_policy" "api" {
  name = "rwc-${var.environment}-api"
}
