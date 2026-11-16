# Uptime monitoring (docs/aws-architecture.md §5.5): alarms, an outside-in canary,
# a dashboard and a cost budget. Every alarm emails through the rwc-alerts topic.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.6"
    }
  }
}

variable "name" {
  type = string
}

variable "region" {
  type = string
}

variable "alert_email" {
  type = string
}

variable "monthly_budget_usd" {
  type = number
}

variable "api_id" {
  type = string
}

variable "api_stage" {
  type = string
}

variable "api_url" {
  type = string
}

variable "alb_arn_suffix" {
  type = string
}

variable "target_group_arn_suffix" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "service_name" {
  type = string
}

variable "desired_count" {
  type = number
}

variable "app_log_group_name" {
  type = string
}

variable "canary_runtime_version" {
  description = "Synthetics Node.js runtime. Check the current one when applying."
  type        = string
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  partition   = data.aws_partition.current.partition
  alarm_topic = [aws_sns_topic.alerts.arn]
  canary_name = substr("${var.name}-health", 0, 21)
}

# ----------------------------------------------------------------- alerts

# CloudWatch can't publish to a topic encrypted with the AWS-managed SNS key,
# so the topic gets its own key that allows CloudWatch.
data "aws_iam_policy_document" "alerts_key" {
  statement {
    sid       = "AccountAdministersKeyThroughIam"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }

  statement {
    sid       = "CloudWatchPublishesAlarms"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey*"]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
  }
}

resource "aws_kms_key" "alerts" {
  description             = "${var.name} alert topic"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.alerts_key.json
}

resource "aws_sns_topic" "alerts" {
  name              = "${var.name}-alerts"
  kms_master_key_id = aws_kms_key.alerts.arn
}

data "aws_iam_policy_document" "alerts_topic" {
  statement {
    sid       = "CloudWatchAlarmsPublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
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
  policy = data.aws_iam_policy_document.alerts_topic.json
}

# The recipient must click the confirmation link AWS emails them.
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------------------------- app metrics from JSON logs

# The app logs one {"event": "ml_request", "service", "status", "latency_ms"} line per
# ML call (backend/app/observability.py); these filters turn them into metrics.
resource "aws_cloudwatch_log_metric_filter" "ml_requests" {
  name           = "${var.name}-ml-requests"
  log_group_name = var.app_log_group_name
  pattern        = "{ $.event = \"ml_request\" }"

  metric_transformation {
    name       = "MLRequests"
    namespace  = "RWC/API"
    value      = "1"
    unit       = "Count"
    dimensions = { Service = "$.service", Status = "$.status" }
  }
}

resource "aws_cloudwatch_log_metric_filter" "ml_latency" {
  name           = "${var.name}-ml-latency"
  log_group_name = var.app_log_group_name
  pattern        = "{ $.event = \"ml_request\" }"

  metric_transformation {
    name       = "MLLatency"
    namespace  = "RWC/API"
    value      = "$.latency_ms"
    unit       = "Milliseconds"
    dimensions = { Service = "$.service" }
  }
}

# ----------------------------------------------------------------- alarms

resource "aws_cloudwatch_metric_alarm" "api_5xx_rate" {
  alarm_name          = "${var.name}-api-5xx-rate"
  alarm_description   = "More than 5% of API requests failed with a 5xx in 5 minutes."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic

  metric_query {
    id          = "rate"
    expression  = "IF(requests > 0, 100 * errors / requests, 0)"
    label       = "5xx %"
    return_data = true
  }

  metric_query {
    id = "errors"

    metric {
      namespace   = "AWS/ApiGateway"
      metric_name = "5xx"
      dimensions  = { ApiId = var.api_id, Stage = var.api_stage }
      stat        = "Sum"
      period      = 300
    }
  }

  metric_query {
    id = "requests"

    metric {
      namespace   = "AWS/ApiGateway"
      metric_name = "Count"
      dimensions  = { ApiId = var.api_id, Stage = var.api_stage }
      stat        = "Sum"
      period      = 300
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${var.name}-api-latency-p95"
  alarm_description   = "p95 API latency above 10 s for 15 minutes (transcription is slow, so this is loose)."
  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  dimensions          = { ApiId = var.api_id, Stage = var.api_stage }
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  comparison_operator = "GreaterThanThreshold"
  threshold           = 10000
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

resource "aws_cloudwatch_metric_alarm" "unhealthy_hosts" {
  alarm_name          = "${var.name}-unhealthy-tasks"
  alarm_description   = "At least one API task is failing its /health check."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  dimensions          = { LoadBalancer = var.alb_arn_suffix, TargetGroup = var.target_group_arn_suffix }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

resource "aws_cloudwatch_metric_alarm" "no_healthy_hosts" {
  alarm_name          = "${var.name}-api-down"
  alarm_description   = "CRITICAL: no healthy API tasks. The API is down."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  dimensions          = { LoadBalancer = var.alb_arn_suffix, TargetGroup = var.target_group_arn_suffix }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

resource "aws_cloudwatch_metric_alarm" "running_tasks" {
  count = var.desired_count > 0 ? 1 : 0

  alarm_name          = "${var.name}-running-tasks"
  alarm_description   = "Fewer API tasks running than the minimum for 5 minutes."
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  dimensions          = { ClusterName = var.cluster_name, ServiceName = var.service_name }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 5
  comparison_operator = "LessThanThreshold"
  threshold           = var.desired_count
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

resource "aws_cloudwatch_metric_alarm" "cpu" {
  alarm_name          = "${var.name}-cpu-high"
  alarm_description   = "API CPU above 80% for 10 minutes (autoscaling should be adding tasks)."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = { ClusterName = var.cluster_name, ServiceName = var.service_name }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

resource "aws_cloudwatch_metric_alarm" "memory" {
  alarm_name          = "${var.name}-memory-high"
  alarm_description   = "API memory above 85% for 10 minutes (Whisper may need a bigger task)."
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  dimensions          = { ClusterName = var.cluster_name, ServiceName = var.service_name }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 85
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

resource "aws_cloudwatch_metric_alarm" "canary" {
  alarm_name          = "${var.name}-canary-failing"
  alarm_description   = "The outside-in health check failed twice in a row (API down, DynamoDB unreachable, or transcription in stub mode)."
  namespace           = "CloudWatchSynthetics"
  metric_name         = "SuccessPercent"
  dimensions          = { CanaryName = aws_synthetics_canary.health.name }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "LessThanThreshold"
  threshold           = 100
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

resource "aws_cloudwatch_metric_alarm" "transcribe_model_errors" {
  alarm_name          = "${var.name}-transcribe-model-errors"
  alarm_description   = "Whisper failed to load or run more than 5 times in 5 minutes (server fault, not bad audio)."
  namespace           = "RWC/API"
  metric_name         = "MLRequests"
  dimensions          = { Service = "transcribe", Status = "model_error" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

resource "aws_cloudwatch_metric_alarm" "transcribe_stub" {
  alarm_name          = "${var.name}-transcribe-stub"
  alarm_description   = "Production served fake (stub) transcriptions: the image was built without INSTALL_SPEECH=1."
  namespace           = "RWC/API"
  metric_name         = "MLRequests"
  dimensions          = { Service = "transcribe", Status = "stub" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_topic
  ok_actions          = local.alarm_topic
}

# ----------------------------------------------------------------- canary

resource "aws_s3_bucket" "canary" {
  #checkov:skip=CKV_AWS_21:Canary artifacts are throwaway and expire after 30 days; no versioning.
  #checkov:skip=CKV_AWS_144:Canary artifacts don't need cross-region replication.
  #checkov:skip=CKV_AWS_18:No access logging for canary artifacts.
  #checkov:skip=CKV_AWS_145:SSE-S3 is enough for screenshots and HAR files of public endpoints.
  #checkov:skip=CKV2_AWS_62:No event notifications needed.
  bucket = "${var.name}-canary-${local.account_id}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "canary" {
  bucket = aws_s3_bucket.canary.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "canary" {
  bucket = aws_s3_bucket.canary.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "canary" {
  bucket = aws_s3_bucket.canary.id

  rule {
    id     = "expire-artifacts"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "canary_bucket_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.canary.arn, "${aws_s3_bucket.canary.arn}/*"]

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

resource "aws_s3_bucket_policy" "canary" {
  bucket = aws_s3_bucket.canary.id
  policy = data.aws_iam_policy_document.canary_bucket_tls_only.json
}

data "aws_iam_policy_document" "canary_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "canary" {
  name               = "${var.name}-canary"
  assume_role_policy = data.aws_iam_policy_document.canary_trust.json
}

# The permissions CloudWatch Synthetics documents as required for a canary.
data "aws_iam_policy_document" "canary" {
  statement {
    sid       = "WriteArtifacts"
    actions   = ["s3:PutObject", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.canary.arn, "${aws_s3_bucket.canary.arn}/*"]
  }

  statement {
    sid       = "ListBuckets"
    actions   = ["s3:ListAllMyBuckets"]
    resources = ["*"] # Required by the Synthetics runtime; can't be scoped.
  }

  statement {
    sid       = "WriteCanaryLogs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${local.partition}:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/cwsyn-*"]
  }

  statement {
    sid       = "PublishCanaryMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"] # PutMetricData can't be scoped; limited to the Synthetics namespace below.

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["CloudWatchSynthetics"]
    }
  }
}

resource "aws_iam_role_policy" "canary" {
  name   = "canary"
  role   = aws_iam_role.canary.id
  policy = data.aws_iam_policy_document.canary.json
}

data "archive_file" "canary" {
  type        = "zip"
  source_dir  = "${path.module}/canary"
  output_path = "${path.module}/.build/canary.zip"
}

resource "aws_synthetics_canary" "health" {
  name                     = local.canary_name
  artifact_s3_location     = "s3://${aws_s3_bucket.canary.bucket}/"
  execution_role_arn       = aws_iam_role.canary.arn
  handler                  = "heartbeat.handler"
  zip_file                 = data.archive_file.canary.output_path
  runtime_version          = var.canary_runtime_version
  start_canary             = true
  success_retention_period = 30
  failure_retention_period = 30

  schedule {
    expression = "rate(5 minutes)"
  }

  run_config {
    timeout_in_seconds    = 60
    environment_variables = { API_URL = var.api_url }
  }
}

# -------------------------------------------------------------- dashboard

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.name

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "API requests and errors"
          region = var.region
          stat   = "Sum"
          period = 300
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", var.api_id, "Stage", var.api_stage],
            [".", "4xx", ".", ".", ".", "."],
            [".", "5xx", ".", ".", ".", "."],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "API latency (ms)"
          region = var.region
          period = 300
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiId", var.api_id, "Stage", var.api_stage, { stat = "p50" }],
            ["...", { stat = "p95" }],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Healthy API tasks"
          region = var.region
          stat   = "Minimum"
          period = 60
          metrics = [
            ["AWS/ApplicationELB", "HealthyHostCount", "TargetGroup", var.target_group_arn_suffix, "LoadBalancer", var.alb_arn_suffix],
            [".", "UnHealthyHostCount", ".", ".", ".", "."],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "API CPU and memory (%)"
          region = var.region
          stat   = "Average"
          period = 300
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", var.cluster_name, "ServiceName", var.service_name],
            [".", "MemoryUtilization", ".", ".", ".", "."],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "ML requests by outcome"
          region = var.region
          period = 300
          metrics = [
            [{ expression = "SEARCH('{RWC/API,Service,Status} MetricName=\"MLRequests\"', 'Sum', 300)", id = "outcomes" }],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Canary success (%)"
          region = var.region
          stat   = "Average"
          period = 300
          metrics = [
            ["CloudWatchSynthetics", "SuccessPercent", "CanaryName", aws_synthetics_canary.health.name],
          ]
        }
      },
    ]
  })
}

# ----------------------------------------------------------------- budget

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "dashboard_url" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "canary_name" {
  value = aws_synthetics_canary.health.name
}
