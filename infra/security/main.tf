# Account security baseline (docs/aws-architecture.md §5.5, docs/security-monitoring.md).
#
# Its own stack because these are account-wide, one-per-region services, not data
# resources: the data stack README lists them as "belongs in an account baseline".
# Apply it right after bootstrap and before the data stack, so the first data resources
# are already being watched. Like the data stack, state is local until a backend is added.
#
# What it watches, and where alerts go:
#   CloudTrail      every management call, plus each read/write of recordings and of the
#                   private learner tables (who touched learner data, and when)
#   GuardDuty       threat detection on CloudTrail, S3 data events and Lambda network logs
#   AWS Config      rules that fail if a bucket goes public, loses encryption or TLS-only,
#                   a table loses backups or its customer-managed key, or key rotation stops
#   Access Analyzer any bucket, key or role that becomes reachable from outside the account
#   Tamper alarms   someone stops the trail, disables a key, turns off a detector, or
#                   uses the root user
# All of them email the security_alert_email address through one encrypted SNS topic.

terraform {
  required_version = ">= 1.6"
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
      project     = "rwc-rohingya-english-app"
      environment = var.environment
      managed_by  = "terraform"
      stack       = "security"
      budget_line = "hosting"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  name       = "rwc-${var.environment}-security"
  trail_name = "rwc-${var.environment}-trail"
  trail_arn  = "arn:${local.partition}:cloudtrail:${var.region}:${local.account_id}:trail/${local.trail_name}"

  # Same names the data stack creates (infra/s3.tf, infra/dynamodb.tf). Looked up by
  # name, not by reference, so this stack can be applied before the data stack.
  recording_buckets = ["${var.name_prefix}-learner-audio", "${var.name_prefix}-research-audio"]
  private_tables = [
    "arn:${local.partition}:dynamodb:${var.region}:${local.account_id}:table/rwc-${var.environment}-progress",
    "arn:${local.partition}:dynamodb:${var.region}:${local.account_id}:table/rwc-${var.environment}-review-log",
  ]
}

# ------------------------------------------------------------------ account settings

# The architecture doc (§4) promises account-wide Block Public Access; the data stack
# only sets it per bucket. This makes it impossible for any new bucket to go public.
resource "aws_s3_account_public_access_block" "this" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Free. Reports any bucket, key, role or table shared outside this account.
resource "aws_accessanalyzer_analyzer" "account" {
  analyzer_name = "${local.name}-analyzer"
  type          = "ACCOUNT"
}

# ------------------------------------------------------------------ encryption key

data "aws_iam_policy_document" "key" {
  #checkov:skip=CKV_AWS_109:Standard account-root statement; in a key policy, resource "*" means this key.
  #checkov:skip=CKV_AWS_111:Same account-root statement.
  #checkov:skip=CKV_AWS_356:In a key policy, resource "*" means this key.
  statement {
    sid       = "AccountRoot"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }

  statement {
    sid       = "CloudTrailEncryptLogs"
    actions   = ["kms:GenerateDataKey*"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:aws:cloudtrail:arn"
      values   = ["arn:${local.partition}:cloudtrail:*:${local.account_id}:trail/*"]
    }
  }

  statement {
    sid       = "CloudTrailDescribeKey"
    actions   = ["kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }

  # EventBridge publishes alerts to the encrypted SNS topic.
  statement {
    sid       = "EventBridgeToEncryptedTopic"
    actions   = ["kms:GenerateDataKey*", "kms:Decrypt"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_kms_key" "security" {
  description             = "rwc security logs and alerts (${var.environment})"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.key.json
}

resource "aws_kms_alias" "security" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.security.key_id
}

# ------------------------------------------------------------------ log bucket

resource "aws_s3_bucket" "logs" {
  #checkov:skip=CKV_AWS_144:Second region deferred (data stack README); CloudTrail log validation detects tampering.
  #checkov:skip=CKV_AWS_18:Access logs for the log bucket would need a second log bucket; CloudTrail already records access to it.
  #checkov:skip=CKV2_AWS_62:No consumers for event notifications; alerts come from EventBridge.
  bucket = "${var.name_prefix}-security-logs"
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.security.arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    id     = "expire-security-logs"
    status = "Enabled"
    filter {}
    expiration {
      days = var.log_retention_days
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
  depends_on = [aws_s3_bucket_versioning.logs]
}

data "aws_iam_policy_document" "logs_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.logs.arn, "${aws_s3_bucket.logs.arn}/*"]
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

  # Evidence must survive an intruder: nobody deletes log files by hand. They leave only
  # through the lifecycle rule above (which isn't an API call, so this doesn't block it).
  # Removing this statement needs the account owner to change the bucket policy, which
  # CloudTrail records and the Config/tamper alarms report.
  statement {
    sid       = "DenyLogDeletion"
    effect    = "Deny"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.logs.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }

  statement {
    sid       = "CloudTrailAclCheck"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.logs.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }

  statement {
    sid       = "CloudTrailWrite"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.logs.arn}/cloudtrail/AWSLogs/${local.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }
}

resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id
  policy = data.aws_iam_policy_document.logs_bucket.json
}

# ------------------------------------------------------------------ CloudTrail

resource "aws_cloudtrail" "this" {
  #checkov:skip=CKV_AWS_252:Alerts come from EventBridge rules below, not a trail SNS topic (which would fire per log file).
  #checkov:skip=CKV2_AWS_10:Not sent to CloudWatch Logs (ingestion cost); EventBridge sees the same management events for alerting.
  name                          = local.trail_name
  s3_bucket_name                = aws_s3_bucket.logs.id
  s3_key_prefix                 = "cloudtrail"
  kms_key_id                    = aws_kms_key.security.arn
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true

  advanced_event_selector {
    name = "All management events"
    field_selector {
      field  = "eventCategory"
      equals = ["Management"]
    }
  }

  # Every read and write of a recording: answers "who listened to or copied this
  # person's voice?" Lexicon media and datasets are public content and not logged.
  advanced_event_selector {
    name = "Recording object access"
    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }
    field_selector {
      field  = "resources.type"
      equals = ["AWS::S3::Object"]
    }
    field_selector {
      field       = "resources.ARN"
      starts_with = [for b in local.recording_buckets : "arn:${local.partition}:s3:::${b}/"]
    }
  }

  # Learner progress and the reviewer audit trail. The public content table isn't
  # logged: it is read on every cache refresh and holds nothing private.
  advanced_event_selector {
    name = "Private table access"
    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }
    field_selector {
      field  = "resources.type"
      equals = ["AWS::DynamoDB::Table"]
    }
    field_selector {
      field  = "resources.ARN"
      equals = local.private_tables
    }
  }

  depends_on = [aws_s3_bucket_policy.logs]
}

# ------------------------------------------------------------------ GuardDuty

resource "aws_guardduty_detector" "this" {
  #checkov:skip=CKV2_AWS_3:One standalone account, no AWS Organization yet; the detector covers this account and region.
  enable                       = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"
}

# Only what this account uses. The others bill per resource scanned, and we run no
# EC2, EBS, EKS or RDS.
locals {
  guardduty_features = {
    S3_DATA_EVENTS         = "ENABLED"
    LAMBDA_NETWORK_LOGS    = "ENABLED"
    EKS_AUDIT_LOGS         = "DISABLED"
    EBS_MALWARE_PROTECTION = "DISABLED"
    RDS_LOGIN_EVENTS       = "DISABLED"
    RUNTIME_MONITORING     = "DISABLED"
  }
}

resource "aws_guardduty_detector_feature" "this" {
  for_each    = local.guardduty_features
  detector_id = aws_guardduty_detector.this.id
  name        = each.key
  status      = each.value
}

# ------------------------------------------------------------------ AWS Config

data "aws_iam_policy_document" "config_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "config" {
  name               = "${local.name}-config"
  assume_role_policy = data.aws_iam_policy_document.config_assume.json
}

resource "aws_iam_role_policy_attachment" "config" {
  role       = aws_iam_role.config.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AWS_ConfigRole"
}

data "aws_iam_policy_document" "config_delivery" {
  statement {
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.logs.arn]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.logs.arn}/config/AWSLogs/${local.account_id}/*"]
  }
  statement {
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [aws_kms_key.security.arn]
  }
}

resource "aws_iam_role_policy" "config_delivery" {
  name   = "deliver-to-security-logs"
  role   = aws_iam_role.config.id
  policy = data.aws_iam_policy_document.config_delivery.json
}

# Records only the resource types the rules check, to keep Config's per-item cost low.
resource "aws_config_configuration_recorder" "this" {
  #checkov:skip=CKV2_AWS_48:Records only the types the rules check, to keep per-item cost inside the hosting line.
  name     = local.name
  role_arn = aws_iam_role.config.arn
  recording_group {
    all_supported  = false
    resource_types = ["AWS::S3::Bucket", "AWS::DynamoDB::Table", "AWS::KMS::Key", "AWS::CloudTrail::Trail"]
  }
}

resource "aws_config_delivery_channel" "this" {
  name           = local.name
  s3_bucket_name = aws_s3_bucket.logs.id
  s3_key_prefix  = "config"
  s3_kms_key_arn = aws_kms_key.security.arn
  depends_on     = [aws_config_configuration_recorder.this, aws_s3_bucket_policy.logs]
}

resource "aws_config_configuration_recorder_status" "this" {
  #checkov:skip=CKV2_AWS_45:Same as the recorder: a deliberate subset of resource types.
  name       = aws_config_configuration_recorder.this.name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.this]
}

# AWS managed rules. Each one matches a promise in docs/aws-architecture.md §4-§6.
locals {
  config_rules = {
    s3-no-public-buckets      = "S3_BUCKET_LEVEL_PUBLIC_ACCESS_PROHIBITED"
    s3-account-public-block   = "S3_ACCOUNT_LEVEL_PUBLIC_ACCESS_BLOCKS_PERIODIC"
    s3-tls-only               = "S3_BUCKET_SSL_REQUESTS_ONLY"
    s3-kms-encryption         = "S3_DEFAULT_ENCRYPTION_KMS"
    dynamodb-pitr             = "DYNAMODB_PITR_ENABLED"
    dynamodb-kms              = "DYNAMODB_TABLE_ENCRYPTED_KMS"
    kms-rotation              = "CMK_BACKING_KEY_ROTATION_ENABLED"
    cloudtrail-log-validation = "CLOUD_TRAIL_LOG_FILE_VALIDATION_ENABLED"
  }
}

resource "aws_config_config_rule" "this" {
  for_each = local.config_rules
  name     = "rwc-${var.environment}-${each.key}"
  source {
    owner             = "AWS"
    source_identifier = each.value
  }
  depends_on = [aws_config_configuration_recorder.this]
}

# ------------------------------------------------------------------ alerts

resource "aws_sns_topic" "alerts" {
  name              = "${local.name}-alerts"
  kms_master_key_id = aws_kms_key.security.arn
}

data "aws_iam_policy_document" "alerts" {
  statement {
    sid       = "EventBridgePublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts.json
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.security_alert_email
}

locals {
  alert_rules = {
    guardduty-finding = {
      description = "GuardDuty finding of medium severity or higher"
      pattern = {
        source      = ["aws.guardduty"]
        detail-type = ["GuardDuty Finding"]
        detail      = { severity = [{ numeric = [">=", var.guardduty_min_severity] }] }
      }
    }
    config-noncompliant = {
      description = "A Config rule found a resource out of compliance"
      pattern = {
        source      = ["aws.config"]
        detail-type = ["Config Rules Compliance Change"]
        detail      = { newEvaluationResult = { complianceType = ["NON_COMPLIANT"] } }
      }
    }
    external-access = {
      description = "Access Analyzer found a resource shared outside the account"
      pattern = {
        source      = ["aws.access-analyzer"]
        detail-type = ["Access Analyzer Finding"]
        detail      = { status = ["ACTIVE"] }
      }
    }
    # Someone switching off the monitoring, or the keys that make data readable.
    tamper = {
      description = "Logging, detection or a data key was disabled or deleted"
      pattern = {
        detail-type = ["AWS API Call via CloudTrail"]
        detail = {
          eventName = [
            "StopLogging", "DeleteTrail", "UpdateTrail", "PutEventSelectors",
            "DeleteDetector", "UpdateDetector",
            "StopConfigurationRecorder", "DeleteConfigurationRecorder", "DeleteDeliveryChannel",
            "DeleteAnalyzer",
            "ScheduleKeyDeletion", "DisableKey", "DisableKeyRotation", "PutKeyPolicy",
            "DeleteAccountPublicAccessBlock", "DeletePublicAccessBlock",
            "DeleteBucketPolicy", "PutBucketPolicy",
            "DeleteTable", "UpdateContinuousBackups",
          ]
        }
      }
    }
    # Root sign-in events are written in us-east-1, so this catches root API calls made
    # in this region. The account owner should also enable root sign-in email alerts.
    root-use = {
      description = "The root user was used"
      pattern = {
        detail-type = ["AWS API Call via CloudTrail", "AWS Console Sign In via CloudTrail"]
        detail      = { userIdentity = { type = ["Root"] } }
      }
    }
  }
}

resource "aws_cloudwatch_event_rule" "alert" {
  for_each      = local.alert_rules
  name          = "rwc-${var.environment}-${each.key}"
  description   = each.value.description
  event_pattern = jsonencode(each.value.pattern)
}

resource "aws_cloudwatch_event_target" "alert" {
  for_each = local.alert_rules
  rule     = aws_cloudwatch_event_rule.alert[each.key].name
  arn      = aws_sns_topic.alerts.arn
}
