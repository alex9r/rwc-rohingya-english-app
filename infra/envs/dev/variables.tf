variable "region" {
  description = "ca-central-1 keeps all data in Canada (spec §1)."
  type        = string
  default     = "ca-central-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "alert_email" {
  description = "Receives alarm and budget emails. Must confirm the SNS subscription email."
  type        = string
}

variable "monthly_budget_usd" {
  type    = number
  default = 100
}

variable "github_oidc_provider_arn" {
  description = "Output of the bootstrap root."
  type        = string
}

variable "github_repo" {
  type    = string
  default = "alex9r/rwc-rohingya-english-app"
}

variable "github_environment" {
  description = "GitHub environment the deploy job runs in. Give it a required reviewer."
  type        = string
  default     = "production"
}

variable "loader_principal_arns" {
  description = "Who may assume the lexicon loader role. Empty = account principals granted sts:AssumeRole."
  type        = list(string)
  default     = []
}

variable "image_tag" {
  description = "Image for the first apply only. GitHub Actions deploys every later image."
  type        = string
  default     = "bootstrap"
}

variable "task_cpu" {
  description = "Fargate CPU units per task (2048 = 2 vCPU). A guess for Whisper small; tune it."
  type        = number
  default     = 2048
}

variable "task_memory" {
  description = "MiB per task. A guess for Whisper small; tune it."
  type        = number
  default     = 4096
}

variable "desired_count" {
  description = "Minimum running tasks (2 = one per AZ). Use 0 for the first apply, before an image exists."
  type        = number
  default     = 2
}

variable "max_count" {
  type    = number
  default = 4
}

variable "throttle_rate" {
  description = "API Gateway steady-state requests per second (whole API)."
  type        = number
  default     = 20
}

variable "throttle_burst" {
  type    = number
  default = 50
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "alb_deletion_protection" {
  type    = bool
  default = true
}

variable "canary_runtime_version" {
  description = "CloudWatch Synthetics Node.js runtime; check the newest one when applying."
  type        = string
  default     = "syn-nodejs-puppeteer-9.1"
}
