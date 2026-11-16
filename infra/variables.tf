variable "region" {
  description = "Primary region. Must be in Canada (data residency)."
  type        = string
  default     = "ca-central-1"

  validation {
    condition     = contains(["ca-central-1", "ca-west-1"], var.region)
    error_message = "Data must stay in Canada: use ca-central-1 or ca-west-1."
  }
}

variable "environment" {
  description = "dev, staging or prod. Use a separate AWS account per environment."
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

variable "name_prefix" {
  description = "Prefix for globally unique S3 bucket names, e.g. rwc-<org>-<env>."
  type        = string
}

variable "learner_audio_retention_days" {
  description = "Days before stored recordings expire automatically. Deletion on request is separate."
  type        = number
  default     = 30
}

variable "research_audio_retention_days" {
  description = "Days research recordings are kept. Set this to what the consent form promises (project length plus a margin)."
  type        = number
  default     = 365
}

variable "log_retention_days" {
  type    = number
  default = 365
}

variable "deletion_protection" {
  description = "Protect tables from deletion. Turn off only in throwaway dev accounts."
  type        = bool
  default     = true
}

variable "progress_ttl_attribute" {
  type    = string
  default = "ttl"
}
