variable "region" {
  description = "Must be in Canada (data residency), as in the data stack."
  type        = string
  default     = "ca-central-1"

  validation {
    condition     = contains(["ca-central-1", "ca-west-1"], var.region)
    error_message = "Data must stay in Canada: use ca-central-1 or ca-west-1."
  }
}

variable "environment" {
  description = "Must match the data stack's environment: its resources are looked up by name."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

variable "alert_email" {
  description = "Receives alarm and budget emails. Must confirm the SNS subscription email."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Default: the funding proposal's $350 hosting line over 8 months."
  type        = number
  default     = 45
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
  description = "Image (git SHA) the function is created with on the full apply. Not needed for the first, targeted apply; GitHub Actions deploys every later image."
  type        = string
  default     = ""
}

variable "memory_size" {
  description = "Lambda MB. CPU scales with it (4096 MB is about 2.3 vCPU). A guess for Whisper small; tune it."
  type        = number
  default     = 4096
}

variable "reserved_concurrency" {
  description = "Cap on concurrent Lambda instances, or null for none. Leave null on new accounts (total limit may be 10)."
  type        = number
  default     = null
}

variable "provisioned_concurrency" {
  description = "Always-warm instances (no cold starts, billed hourly). 0 = rely on on-demand plus the canary keeping one warm."
  type        = number
  default     = 0
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

variable "canary_runtime_version" {
  description = "CloudWatch Synthetics Node.js runtime; check the newest one when applying."
  type        = string
  default     = "syn-nodejs-puppeteer-9.1"
}
