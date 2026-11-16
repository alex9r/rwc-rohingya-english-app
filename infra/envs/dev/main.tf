locals {
  name = "rwc-${var.environment}"
}

module "network" {
  source = "../../modules/network"

  name   = local.name
  region = var.region
}

module "data" {
  source = "../../modules/data"

  name       = local.name
  table_name = "${local.name}-content"
}

module "ecr" {
  source = "../../modules/ecr"

  name = "${local.name}-api"
}

module "iam" {
  source = "../../modules/iam"

  name                     = local.name
  region                   = var.region
  ecr_repository_arn       = module.ecr.repository_arn
  log_group_arn            = module.service.log_group_arn
  table_arn                = module.data.table_arn
  kms_key_arn              = module.data.kms_key_arn
  ecs_service_arn          = module.service.service_arn
  github_oidc_provider_arn = var.github_oidc_provider_arn
  github_repo              = var.github_repo
  github_environment       = var.github_environment
  loader_principal_arns    = var.loader_principal_arns
}

module "service" {
  source = "../../modules/service"

  name                    = local.name
  region                  = var.region
  vpc_id                  = module.network.vpc_id
  vpc_cidr                = module.network.cidr_block
  subnet_ids              = module.network.private_subnet_ids
  gateway_prefix_list_ids = module.network.gateway_prefix_list_ids
  image                   = "${module.ecr.repository_url}:${var.image_tag}"
  execution_role_arn      = module.iam.execution_role_arn
  task_role_arn           = module.iam.task_role_arn
  cpu                     = var.task_cpu
  memory                  = var.task_memory
  desired_count           = var.desired_count
  max_count               = var.max_count
  log_retention_days      = var.log_retention_days
  alb_deletion_protection = var.alb_deletion_protection

  # Changes here reach running tasks on the next GitHub Actions deploy
  # (it copies the latest task definition and swaps in the new image).
  # HF_HUB_OFFLINE: the Whisper model is baked into the image, so never download at runtime.
  # CORS_ORIGINS: empty, because the native app doesn't need CORS.
  environment = {
    VOCAB_BACKEND  = "dynamodb"
    VOCAB_TABLE    = module.data.table_name
    AWS_REGION     = var.region
    LOG_FORMAT     = "json"
    HF_HUB_OFFLINE = "1"
    CORS_ORIGINS   = ""
  }
}

module "api" {
  source = "../../modules/api"

  name                  = local.name
  vpc_id                = module.network.vpc_id
  subnet_ids            = module.network.private_subnet_ids
  alb_listener_arn      = module.service.alb_listener_arn
  alb_security_group_id = module.service.alb_security_group_id
  throttle_rate         = var.throttle_rate
  throttle_burst        = var.throttle_burst
  log_retention_days    = var.log_retention_days
}

module "monitoring" {
  source = "../../modules/monitoring"

  name                    = local.name
  region                  = var.region
  alert_email             = var.alert_email
  monthly_budget_usd      = var.monthly_budget_usd
  api_id                  = module.api.api_id
  api_stage               = module.api.stage_name
  api_url                 = module.api.api_url
  alb_arn_suffix          = module.service.alb_arn_suffix
  target_group_arn_suffix = module.service.target_group_arn_suffix
  cluster_name            = module.service.cluster_name
  service_name            = module.service.service_name
  desired_count           = var.desired_count
  app_log_group_name      = module.service.log_group_name
  canary_runtime_version  = var.canary_runtime_version
}
