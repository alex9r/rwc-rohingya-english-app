# One key per sensitivity level, so access can be granted (and revoked) independently.
locals {
  keys = toset(["content", "learner-data", "learner-audio", "research-audio"])
}

resource "aws_kms_key" "this" {
  for_each                = local.keys
  description             = "rwc ${each.key} (${var.environment})"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "this" {
  for_each      = local.keys
  name          = "alias/rwc-${var.environment}-${each.key}"
  target_key_id = aws_kms_key.this[each.key].key_id
}
