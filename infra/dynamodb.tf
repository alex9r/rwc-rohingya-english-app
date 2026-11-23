# All tables: on-demand, PITR, customer-managed KMS, deletion protection. Streams are on
# so global-table replicas (ca-west-1) can be added later; see README "Not yet included".

# Public lexicon. Item types share pk = ENTRY#<id>:
#   META, TR#<role>#<n>, MEDIA#<kind>#<n>, SRC#<kind>#<n>, CONF#<kind>#<timestamp>
resource "aws_dynamodb_table" "content" {
  name                        = "rwc-${var.environment}-content"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = var.deletion_protection
  stream_enabled              = true
  stream_view_type            = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  attribute {
    name = "gsi1pk"
    type = "S"
  }
  attribute {
    name = "gsi1sk"
    type = "S"
  }
  attribute {
    name = "gsi2pk"
    type = "S"
  }
  attribute {
    name = "gsi2sk"
    type = "S"
  }

  # Browse by category: gsi1pk = CATEGORY#<id>, gsi1sk = <english>
  global_secondary_index {
    name            = "gsi1-category"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  # Review queue: gsi2pk = STATUS#<verification_status>, gsi2sk = <confidence>#<id>
  global_secondary_index {
    name            = "gsi2-review"
    hash_key        = "gsi2pk"
    range_key       = "gsi2sk"
    projection_type = "KEYS_ONLY"
  }

  point_in_time_recovery {
    enabled = true
  }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.this["content"].arn
  }
}

# Private learner data: pk = LEARNER#<random uuid>. No names, emails or phone numbers.
resource "aws_dynamodb_table" "progress" {
  name                        = "rwc-${var.environment}-progress"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = var.deletion_protection
  stream_enabled              = true
  stream_view_type            = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = var.progress_ttl_attribute
    enabled        = true
  }
  point_in_time_recovery {
    enabled = true
  }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.this["learner-data"].arn
  }
}

# Append-only audit trail of reviewer actions and corrections.
#   pk = ENTRY#<id>, sk = <ISO timestamp>#<reviewer pseudonym>
#   attributes: action (status_change | correction_proposed | correction_decided),
#   field, previous_value, proposed_value, decision, reason.
# Recording deletions are logged here too, under pk = DELETION#<speaker pseudonym>.
resource "aws_dynamodb_table" "review_log" {
  name                        = "rwc-${var.environment}-review-log"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.this["content"].arn
  }
}
