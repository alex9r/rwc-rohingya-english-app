# The API as a Lambda function running the backend's container image.
#
# The image is the same one docker compose runs: the AWS Lambda Web Adapter inside it
# forwards each API Gateway event to uvicorn on port 8000. The deploy workflow owns the
# code (it publishes a version per image and moves the "live" alias), so Terraform
# ignores image_uri and the alias's version after the first apply.
#
# No VPC: the function reaches DynamoDB, S3 and CloudWatch on their public AWS
# endpoints over TLS, authorised by its IAM role. Nothing can connect to it except
# through API Gateway. (Replaces the Fargate design; see docs/aws-architecture.md §1a.)

terraform {
  required_version = ">= 1.6"

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

variable "image_uri" {
  description = "ECR image for the first create. Later images come from the deploy workflow."
  type        = string
}

variable "role_arn" {
  type = string
}

variable "memory_size" {
  description = "MB. CPU scales with memory (1,769 MB = 1 vCPU, 10,240 MB = 6 vCPU), which sets Whisper's speed."
  type        = number
}

variable "timeout" {
  description = "Seconds. API Gateway HTTP APIs stop waiting after 30 s, so longer is pointless."
  type        = number
  default     = 30
}

variable "ephemeral_storage_mb" {
  description = "/tmp size. Uploads are spooled there."
  type        = number
  default     = 1024
}

variable "reserved_concurrency" {
  description = "Cap on concurrent instances, or null for none. New accounts may have a total limit of 10, which makes any reservation fail; API Gateway throttling limits load either way."
  type        = number
  default     = null
}

variable "provisioned_concurrency" {
  description = "Instances kept warm on the live alias (no cold starts, billed every hour). 0 = none."
  type        = number
  default     = 0
}

variable "environment" {
  type = map(string)
}

variable "log_retention_days" {
  type = number
}

resource "aws_cloudwatch_log_group" "api" {
  #checkov:skip=CKV_AWS_158:AWS-managed encryption; the app never logs request bodies, transcripts or query strings.
  #checkov:skip=CKV_AWS_338:Retention is set by log_retention_days on purpose.
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  #checkov:skip=CKV_AWS_117:No VPC on purpose: no NAT or endpoint cost, and DynamoDB/S3/CloudWatch are reached over TLS with IAM (docs/aws-architecture.md §1a).
  #checkov:skip=CKV_AWS_116:Synchronous API calls; a dead-letter queue only applies to async invokes.
  #checkov:skip=CKV_AWS_173:Environment holds no secrets (table name, log format, flags); AWS-managed encryption is enough.
  #checkov:skip=CKV_AWS_272:Images are built and pushed only by the protected GitHub deploy role; code signing doesn't apply to images.
  #checkov:skip=CKV_AWS_50:X-Ray not used; request IDs and JSON logs cover tracing for one function.
  #checkov:skip=CKV_AWS_115:Concurrency is optional (reserved_concurrency); API Gateway throttling caps load.
  function_name = var.name
  role          = var.role_arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["x86_64"]
  memory_size   = var.memory_size
  timeout       = var.timeout
  publish       = true # version 1 for the alias; the workflow publishes the rest

  reserved_concurrent_executions = var.reserved_concurrency == null ? -1 : var.reserved_concurrency

  ephemeral_storage {
    size = var.ephemeral_storage_mb
  }

  environment {
    variables = var.environment
  }

  # Text: the app's own lines are already JSON (LOG_FORMAT=json), so they reach
  # CloudWatch unchanged and the metric filters can parse them.
  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  lifecycle {
    ignore_changes = [image_uri]

    precondition {
      condition     = !endswith(var.image_uri, ":")
      error_message = "Set image_tag to the git SHA the Deploy workflow pushed (infra/README.md, first deployment step 5)."
    }
  }
}

# API Gateway calls "live". A deploy publishes a new version and moves the alias; a
# failed smoke test moves it back. Config changes made here (env vars, memory) are in
# the next published version, so they reach traffic on the next deploy.
resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.api.function_name
  function_version = aws_lambda_function.api.version

  lifecycle {
    ignore_changes = [function_version]
  }
}

resource "aws_lambda_provisioned_concurrency_config" "live" {
  count                             = var.provisioned_concurrency > 0 ? 1 : 0
  function_name                     = aws_lambda_function.api.function_name
  qualifier                         = aws_lambda_alias.live.name
  provisioned_concurrent_executions = var.provisioned_concurrency
}

output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "alias_name" {
  value = aws_lambda_alias.live.name
}

output "alias_invoke_arn" {
  value = aws_lambda_alias.live.invoke_arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.api.name
}

output "timeout" {
  value = var.timeout
}
