# Least-privilege policies, created but not attached: attach them to the API's Lambda or
# ECS task role once the compute choice is made (see README).

data "aws_iam_policy_document" "api" {
  statement {
    sid     = "ReadContent"
    actions = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:BatchGetItem"]
    resources = [
      aws_dynamodb_table.content.arn,
      "${aws_dynamodb_table.content.arn}/index/*",
    ]
  }
  statement {
    sid = "LearnerProgress"
    actions = [
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query",
      "dynamodb:DeleteItem", "dynamodb:BatchWriteItem",
    ]
    resources = [aws_dynamodb_table.progress.arn]
  }
  statement {
    sid       = "UploadRecordingsOnly"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this["learner-audio"].arn}/*"]
  }
  statement {
    sid     = "UseKeys"
    actions = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [
      aws_kms_key.this["content"].arn,
      aws_kms_key.this["learner-data"].arn,
      aws_kms_key.this["learner-audio"].arn,
    ]
  }
}

# Reviewers (native speakers via the Centre) add to the log and update content status.
data "aws_iam_policy_document" "reviewer" {
  statement {
    sid       = "AppendReviewLog"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.review_log.arn]
    # Limits what a reviewer can write. IAM cannot stop a PutItem from overwriting an
    # existing item: writers must use ConditionExpression "attribute_not_exists(pk)".
    # Update/Delete are denied for everyone by the table's resource policy below.
    condition {
      test     = "ForAllValues:StringEquals"
      variable = "dynamodb:Attributes"
      values   = ["pk", "sk", "action", "field", "previous_value", "proposed_value", "decision", "reason"]
    }
  }
  statement {
    sid       = "UpdateContentStatus"
    actions   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.content.arn, "${aws_dynamodb_table.content.arn}/index/*"]
  }
  statement {
    sid       = "UseContentKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.this["content"].arn]
  }
}

# Used only by `python -m app.recordings delete-speaker`, run by the data holder.
# Covers both recording buckets so a request can never leave research copies behind.
data "aws_iam_policy_document" "recording_deleter" {
  statement {
    sid     = "ListAndDeleteRecordings"
    actions = ["s3:ListBucketVersions", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.this["learner-audio"].arn,
      aws_s3_bucket.this["research-audio"].arn,
    ]
  }
  statement {
    sid     = "DeleteEveryVersion"
    actions = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = [
      "${aws_s3_bucket.this["learner-audio"].arn}/*",
      "${aws_s3_bucket.this["research-audio"].arn}/*",
    ]
  }
  statement {
    sid       = "LogDeletion"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.review_log.arn]
  }
}

# Resource policy on the table itself, so it applies to every principal in the account
# (including admins) without needing to be attached to anyone.
data "aws_iam_policy_document" "review_log_append_only" {
  statement {
    sid       = "ReviewLogIsAppendOnly"
    effect    = "Deny"
    actions   = ["dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem"]
    resources = [aws_dynamodb_table.review_log.arn]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_dynamodb_resource_policy" "review_log" {
  resource_arn = aws_dynamodb_table.review_log.arn
  policy       = data.aws_iam_policy_document.review_log_append_only.json
}

# The data holder uploads consented Centre recordings. No read or delete here.
data "aws_iam_policy_document" "research_uploader" {
  statement {
    sid       = "UploadResearchRecordings"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this["research-audio"].arn}/*"]
  }
  statement {
    sid       = "EncryptWithResearchKey"
    actions   = ["kms:GenerateDataKey"]
    resources = [aws_kms_key.this["research-audio"].arn]
  }
}

# For the SageMaker execution role: read research recordings, nothing else. It can't see
# learner-audio (different bucket and key). Training jobs must take their file list from
# app.recordings.training_recordings(), which filters to model_training consent.
data "aws_iam_policy_document" "research_reader" {
  statement {
    sid       = "ListResearchRecordings"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.this["research-audio"].arn]
  }
  statement {
    sid       = "ReadResearchRecordings"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this["research-audio"].arn}/*"]
  }
  statement {
    sid       = "DecryptWithResearchKey"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.this["research-audio"].arn]
  }
}

resource "aws_iam_policy" "research_uploader" {
  name   = "rwc-${var.environment}-research-uploader"
  policy = data.aws_iam_policy_document.research_uploader.json
}

resource "aws_iam_policy" "research_reader" {
  name   = "rwc-${var.environment}-research-reader"
  policy = data.aws_iam_policy_document.research_reader.json
}

resource "aws_iam_policy" "api" {
  name   = "rwc-${var.environment}-api"
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_iam_policy" "reviewer" {
  name   = "rwc-${var.environment}-reviewer"
  policy = data.aws_iam_policy_document.reviewer.json
}

resource "aws_iam_policy" "recording_deleter" {
  name   = "rwc-${var.environment}-recording-deleter"
  policy = data.aws_iam_policy_document.recording_deleter.json
}
