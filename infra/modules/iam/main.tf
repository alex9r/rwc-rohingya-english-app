# One role per job, scoped to specific resource ARNs (docs/aws-architecture.md §5.2).
# The only "*" resources are actions AWS doesn't allow to be scoped; each is marked.
#
# What the API may do with data is decided by the data stack (infra/iam.tf, the
# rwc-<env>-api policy). This module attaches that policy unchanged and adds only:
#   - dynamodb:Scan on the content table (the API's lexicon cache reads it in one scan)
#   - a Deny that limits the data keys to use through DynamoDB or S3 (kms:ViaService)

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

variable "region" {
  type = string
}

variable "function_name" {
  description = "The API's Lambda function. ARNs are built from it so the roles can exist before the function does (first deploy)."
  type        = string
}

variable "ecr_repository_arn" {
  type = string
}

variable "api_policy_arn" {
  description = "The data stack's rwc-<env>-api policy (infra/iam.tf), attached as is."
  type        = string
}

variable "content_table_arn" {
  description = "The data stack's content table."
  type        = string
}

variable "content_key_arn" {
  description = "The data stack's content KMS key (encrypts the content table)."
  type        = string
}

variable "data_key_arns" {
  description = "Every data-stack key the api policy grants (content, learner-data, learner-audio). The ViaService Deny covers these."
  type        = list(string)
}

variable "github_oidc_provider_arn" {
  description = "From the bootstrap root's output."
  type        = string
}

variable "github_repo" {
  description = "owner/name, exactly as on GitHub."
  type        = string
}

variable "github_environment" {
  description = "Only workflow jobs running in this GitHub environment can deploy."
  type        = string
}

variable "loader_principal_arns" {
  description = "Who may assume the loader role. Empty = any principal in this account that is granted sts:AssumeRole on it."
  type        = list(string)
  default     = []
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  partition     = data.aws_partition.current.partition
  function_arn  = "arn:${local.partition}:lambda:${var.region}:${local.account_id}:function:${var.function_name}"
  log_group_arn = "arn:${local.partition}:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/${var.function_name}"

  via_dynamodb = "dynamodb.${var.region}.amazonaws.com"
  via_s3       = "s3.${var.region}.amazonaws.com"
}

# ------------------------------------------------ the API's Lambda function

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${var.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

# The data stack's decision about what the API may touch (content read, learner
# progress, recording uploads), unchanged.
resource "aws_iam_role_policy_attachment" "api_data" {
  role       = aws_iam_role.api.name
  policy_arn = var.api_policy_arn
}

data "aws_iam_policy_document" "api_supplement" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${local.log_group_arn}:*"]
  }

  # app.vocabulary_dynamo loads the whole lexicon (~100 entries) with one Scan and
  # caches it. The api policy above allows GetItem/Query/BatchGetItem but not Scan.
  # The content is public, and the API can already read every item, so Scan exposes
  # nothing new; it's limited to the content table (not progress or the review log).
  statement {
    sid       = "ScanContent"
    actions   = ["dynamodb:Scan"]
    resources = [var.content_table_arn]
  }

  # The api policy grants kms:Decrypt/GenerateDataKey on the data keys with no
  # condition, so the API's credentials could call KMS directly. This Deny allows key
  # use only when DynamoDB or S3 makes the call on the API's behalf. An explicit Deny
  # overrides the Allow without editing the data stack. A direct call carries no
  # kms:ViaService, and StringNotEquals is true for a missing key, so it is denied.
  statement {
    sid       = "DataKeysOnlyViaDynamoDbOrS3"
    effect    = "Deny"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey*"]
    resources = var.data_key_arns

    condition {
      test     = "StringNotEquals"
      variable = "kms:ViaService"
      values   = [local.via_dynamodb, local.via_s3]
    }
  }
}

resource "aws_iam_role_policy" "api_supplement" {
  name   = "api-supplement"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_supplement.json
}

# --------------------------------- loader: python -m app.dynamo_load, by a person
# The data stack has no role that can create content items (reviewers can only update
# existing ones), so the initial load and new dataset entries go through this role.

data "aws_iam_policy_document" "loader_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type = "AWS"
      identifiers = (
        length(var.loader_principal_arns) > 0
        ? var.loader_principal_arns
        : ["arn:${local.partition}:iam::${local.account_id}:root"]
      )
    }
  }
}

resource "aws_iam_role" "loader" {
  name               = "${var.name}-content-loader"
  assume_role_policy = data.aws_iam_policy_document.loader_trust.json
}

data "aws_iam_policy_document" "loader" {
  # PutItem only: the loader writes one item at a time, insert-only by default so it
  # never overwrites a reviewer's correction (--overwrite is a deliberate choice).
  statement {
    sid       = "WriteLexicon"
    actions   = ["dynamodb:PutItem"]
    resources = [var.content_table_arn]
  }

  statement {
    sid       = "EncryptLexicon"
    actions   = ["kms:Decrypt", "kms:DescribeKey", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [var.content_key_arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = [local.via_dynamodb]
    }
  }
}

resource "aws_iam_role_policy" "loader" {
  name   = "write-lexicon"
  role   = aws_iam_role.loader.id
  policy = data.aws_iam_policy_document.loader.json
}

# ------------------------------- GitHub Actions: push the image and deploy it

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Only jobs in the protected environment (which needs a reviewer) can assume this.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${var.name}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # Can't be scoped to a resource.
  }

  # Push, plus the two read actions Lambda checks on the caller when the function's
  # code is pointed at a new image.
  statement {
    sid = "PushApiImage"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [var.ecr_repository_arn]
  }

  # New image -> new published version -> move the "live" alias (and back, on a
  # failed smoke test). No iam:PassRole: updating code doesn't change the role.
  statement {
    sid = "DeployApiFunction"
    actions = [
      "lambda:GetAlias",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:PublishVersion",
      "lambda:UpdateAlias",
      "lambda:UpdateFunctionCode",
    ]
    resources = [local.function_arn, "${local.function_arn}:*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "deploy-api"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

output "api_role_arn" {
  value = aws_iam_role.api.arn
}

output "loader_role_arn" {
  value = aws_iam_role.loader.arn
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}
