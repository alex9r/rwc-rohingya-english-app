locals {
  buckets = {
    media         = { key = "content", versioned = true }
    datasets      = { key = "content", versioned = true }
    logs          = { key = "content", versioned = true }
    learner-audio = { key = "learner-audio", versioned = false }
    # Consented Centre recordings for benchmarking and fine-tuning. Versioned so a
    # mistake can't lose the dataset; the delete-speaker command removes every version.
    research-audio = { key = "research-audio", versioned = true }
  }
}

# Accepted exception: learner-audio is unversioned on purpose (see aws_s3_bucket_versioning).
#trivy:ignore:AVD-AWS-0090
resource "aws_s3_bucket" "this" {
  for_each = local.buckets
  bucket   = "${var.name_prefix}-${each.key}"

  # Released lexicon snapshots can't be silently altered or removed.
  object_lock_enabled = each.key == "datasets"
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = local.buckets
  bucket                  = aws_s3_bucket.this[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this[each.value.key].arn
    }
  }
}

# learner-audio is deliberately NOT versioned: with versioning, "delete" would leave
# recoverable copies behind. Deleting a recording there really removes it.
resource "aws_s3_bucket_versioning" "this" {
  for_each = { for k, v in local.buckets : k => v if v.versioned }
  bucket   = aws_s3_bucket.this[each.key].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "datasets" {
  bucket = aws_s3_bucket.this["datasets"].id
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 365
    }
  }
  depends_on = [aws_s3_bucket_versioning.this]
}

data "aws_iam_policy_document" "bucket" {
  for_each = local.buckets

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this[each.key].arn, "${aws_s3_bucket.this[each.key].arn}/*"]
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

  statement {
    sid       = "DenyUnencryptedUploads"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this[each.key].arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  for_each = { for k in keys(local.buckets) : k => k if k != "media" }
  bucket   = aws_s3_bucket.this[each.key].id
  policy   = data.aws_iam_policy_document.bucket[each.key].json
}

resource "aws_s3_bucket_lifecycle_configuration" "learner_audio" {
  bucket = aws_s3_bucket.this["learner-audio"].id
  rule {
    id     = "expire-recordings"
    status = "Enabled"
    filter {}
    expiration {
      days = var.learner_audio_retention_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "research_audio" {
  bucket = aws_s3_bucket.this["research-audio"].id
  rule {
    id     = "expire-research-recordings"
    status = "Enabled"
    filter {}
    expiration {
      days = var.research_audio_retention_days
    }
    # Old versions (overwritten files) don't linger past a week.
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
  depends_on = [aws_s3_bucket_versioning.this]
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.this["logs"].id
  rule {
    id     = "expire-logs"
    status = "Enabled"
    filter {}
    expiration {
      days = var.log_retention_days
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}
