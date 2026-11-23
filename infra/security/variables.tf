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
  description = "dev, staging or prod. Must match the data stack."
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

variable "name_prefix" {
  description = "Same name_prefix as the data stack: used to find the recording buckets and to name the security log bucket."
  type        = string
}

variable "security_alert_email" {
  description = "Who receives security alerts. Should be the privacy lead or a shared inbox they read, not one developer's personal address."
  type        = string
}

variable "log_retention_days" {
  description = "Days CloudTrail and Config records are kept. Matches the data stack's log bucket (1 year)."
  type        = number
  default     = 365
}

variable "guardduty_min_severity" {
  description = "Lowest GuardDuty severity that emails. 4 = medium, 7 = high."
  type        = number
  default     = 4
}
