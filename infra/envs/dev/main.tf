# Compute, API and monitoring for the dev environment. The data layer (tables, buckets,
# keys, data policies) is the separate data stack in infra/; see data.tf.

locals {
  name          = "rwc-${var.environment}"
  function_name = "${local.name}-api"
}

module "ecr" {
  source = "../../modules/ecr"

  name = "${local.name}-api"
}

module "iam" {
  source = "../../modules/iam"

  name                     = local.name
  region                   = var.region
  function_name            = local.function_name
  ecr_repository_arn       = module.ecr.repository_arn
  api_policy_arn           = data.aws_iam_policy.api.arn
  content_table_arn        = data.aws_dynamodb_table.content.arn
  content_key_arn          = data.aws_kms_alias.data["content"].target_key_arn
  data_key_arns            = [for k in local.data_keys : data.aws_kms_alias.data[k].target_key_arn]
  github_oidc_provider_arn = var.github_oidc_provider_arn
  github_repo              = var.github_repo
  github_environment       = var.github_environment
  loader_principal_arns    = var.loader_principal_arns
}

module "function" {
  source = "../../modules/function"

  name                    = local.function_name
  image_uri               = "${module.ecr.repository_url}:${var.image_tag}"
  role_arn                = module.iam.api_role_arn
  memory_size             = var.memory_size
  reserved_concurrency    = var.reserved_concurrency
  provisioned_concurrency = var.provisioned_concurrency
  log_retention_days      = var.log_retention_days

  # Reaches traffic on the next deploy (the workflow publishes a new version, which
  # picks up the latest configuration).
  # AWS_REGION is not set here: Lambda reserves it and sets it itself.
  environment = {
    VOCAB_BACKEND = "dynamodb"
    VOCAB_TABLE   = data.aws_dynamodb_table.content.name
    LOG_FORMAT    = "json"
    # The Whisper model is baked into the image; never download at runtime.
    HF_HUB_OFFLINE = "1"
    # Empty: the native app doesn't need CORS. Set it for the Expo web build.
    CORS_ORIGINS = ""
    # Lambda's request payload limit is 6 MB and binary uploads arrive base64-encoded
    # (a third larger), so cap raw uploads at 4 MiB to get a clean 413 instead.
    MAX_UPLOAD_BYTES = "4194304"
    # Load Whisper in a thread: Lambda's init phase is limited to about 10 s.
    RWC_WARMUP = "background"
    # Lambda Web Adapter: where uvicorn listens, and the path that says it's ready.
    AWS_LWA_PORT                 = "8000"
    AWS_LWA_READINESS_CHECK_PATH = "/health"
    # Only /tmp is writable on Lambda.
    TMPDIR         = "/tmp"
    XDG_CACHE_HOME = "/tmp"
  }
}

module "api" {
  source = "../../modules/api"

  name               = local.name
  function_name      = module.function.function_name
  alias_name         = module.function.alias_name
  alias_invoke_arn   = module.function.alias_invoke_arn
  throttle_rate      = var.throttle_rate
  throttle_burst     = var.throttle_burst
  log_retention_days = var.log_retention_days
}

module "monitoring" {
  source = "../../modules/monitoring"

  name                   = local.name
  region                 = var.region
  alert_email            = var.alert_email
  monthly_budget_usd     = var.monthly_budget_usd
  api_id                 = module.api.api_id
  api_stage              = module.api.stage_name
  api_url                = module.api.api_url
  function_name          = module.function.function_name
  function_timeout       = module.function.timeout
  app_log_group_name     = module.function.log_group_name
  canary_runtime_version = var.canary_runtime_version
}
