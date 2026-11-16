# One role per job, scoped to specific resource ARNs (docs/aws-architecture.md §5.2).
# The only "*" resources are actions AWS doesn't allow to be scoped; each is marked.

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

variable "region" {
  type = string
}

variable "ecr_repository_arn" {
  type = string
}

variable "log_group_arn" {
  type = string
}

variable "table_arn" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "ecs_service_arn" {
  type = string
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
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  # KMS use only through DynamoDB, never directly.
  via_dynamodb = "dynamodb.${var.region}.amazonaws.com"
}

data "aws_iam_policy_document" "ecs_tasks_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

# ----------------------------------------- task execution: start the container

resource "aws_iam_role" "execution" {
  name               = "${var.name}-api-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
}

data "aws_iam_policy_document" "execution" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # GetAuthorizationToken can't be scoped to a resource.
  }

  statement {
    sid       = "PullApiImage"
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [var.ecr_repository_arn]
  }

  statement {
    sid       = "WriteApiLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${var.log_group_arn}:*"]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "execution"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

# ------------------------------------------------- task: what the app can do

resource "aws_iam_role" "task" {
  name               = "${var.name}-api-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
}

# Read-only: the API never writes the lexicon.
data "aws_iam_policy_document" "task" {
  statement {
    sid       = "ReadLexicon"
    actions   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
    resources = [var.table_arn, "${var.table_arn}/index/*"]
  }

  statement {
    sid       = "DecryptLexicon"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [var.kms_key_arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = [local.via_dynamodb]
    }
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "read-lexicon"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# --------------------------------- loader: python -m app.dynamo_load, by a person

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
  statement {
    sid       = "WriteLexicon"
    actions   = ["dynamodb:BatchWriteItem", "dynamodb:PutItem"]
    resources = [var.table_arn]
  }

  statement {
    sid       = "EncryptLexicon"
    actions   = ["kms:Decrypt", "kms:DescribeKey", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]

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

  statement {
    sid = "PushApiImage"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [var.ecr_repository_arn]
  }

  statement {
    sid       = "TaskDefinitions"
    actions   = ["ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition"]
    resources = ["*"] # Neither action supports resource-level permissions.
  }

  statement {
    sid       = "DeployApiService"
    actions   = ["ecs:DescribeServices", "ecs:UpdateService"]
    resources = [var.ecs_service_arn]
  }

  statement {
    sid       = "PassTaskRoles"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.task.arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "deploy-api"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

output "execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "loader_role_arn" {
  value = aws_iam_role.loader.arn
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}
