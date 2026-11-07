variable "region" { type = string }
variable "home_region" { type = string }
variable "compartment_id" { type = string }
variable "project_id" { type = string }
variable "instance_id" { type = string }
variable "bundle_path" { type = string }
variable "bundle_sha256" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{64}$", var.bundle_sha256))
    error_message = "Supply the SHA-256 of the bundle."
  }
}
variable "manifest_sha256" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{64}$", var.manifest_sha256))
    error_message = "Supply the SHA-256 of the release manifest."
  }
}
variable "release_alias" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-][A-Za-z0-9_.-]*$", var.release_alias))
    error_message = "Release alias must be a safe directory/command argument."
  }
}
variable "app_version" { type = string }
variable "profile" {
  type    = string
  default = "DEFAULT"
}
variable "name" {
  type    = string
  default = "oci-agent-launchpad"
}
variable "staging_root" {
  type    = string
  default = "/var/ocarun_staging/launchpad"
  validation {
    condition     = can(regex("^/[A-Za-z0-9_/-]+$", var.staging_root)) && !strcontains(var.staging_root, "..")
    error_message = "Use an absolute safe staging path."
  }
}

variable "release_metadata_path" {
  type        = string
  default     = null
  description = "Optional verified release.json; stored next to the immutable ZIP."
}

variable "create_deployment_policy" {
  type        = bool
  default     = true
  description = "False only when an existing policy owner grants this pipeline its required permissions."
}
variable "additional_pipeline_ids" {
  type        = list(string)
  default     = []
  description = "Exact extra deployment pipeline principals managed by this policy owner."
  validation {
    condition     = alltrue([for id in var.additional_pipeline_ids : can(regex("^ocid1\\.devopsdeploypipeline\\.[A-Za-z0-9._-]+$", id))])
    error_message = "Use exact deployment pipeline OCIDs."
  }
}

variable "post_deploy_check_command" {
  type        = string
  default     = null
  description = "Optional preinstalled root-owned verifier under /usr/local/sbin; receives release alias. No inline shell or secrets."
  validation {
    condition     = var.post_deploy_check_command == null ? true : can(regex("^/usr/local/sbin/[A-Za-z0-9_-]+$", var.post_deploy_check_command))
    error_message = "Use a single executable path under /usr/local/sbin without arguments."
  }
}
variable "post_deploy_check_timeout_seconds" {
  type    = number
  default = 300
  validation {
    condition     = var.post_deploy_check_timeout_seconds >= 30 && var.post_deploy_check_timeout_seconds <= 600 && floor(var.post_deploy_check_timeout_seconds) == var.post_deploy_check_timeout_seconds
    error_message = "Verification timeout must be an integer from 30 to 600 seconds."
  }
}
