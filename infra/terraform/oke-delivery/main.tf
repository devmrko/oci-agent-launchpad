terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    oci = { source = "oracle/oci", version = "8.29.0" }
  }
}
provider "oci" { region = var.region }
variable "region" { type = string }
variable "project_id" { type = string }
variable "cluster_id" { type = string }
variable "private_subnet_id" { type = string }
variable "name" {
  type    = string
  default = "launchpad-service-desk-oke"
}
resource "oci_devops_deploy_environment" "oke" {
  deploy_environment_type = "OKE_CLUSTER"
  project_id              = var.project_id
  cluster_id              = var.cluster_id
  display_name            = var.name
  description             = "Private OKE target; runtime secrets and workload IAM managed separately"
  network_channel {
    network_channel_type = "PRIVATE_ENDPOINT_CHANNEL"
    subnet_id            = var.private_subnet_id
  }
}
resource "oci_devops_deploy_pipeline" "oke" {
  project_id   = var.project_id
  display_name = var.name
  description  = "Companion-operated OKE deployment; stages added after runtime prerequisites"
}
output "environment_id" { value = oci_devops_deploy_environment.oke.id }
output "pipeline_id" { value = oci_devops_deploy_pipeline.oke.id }

variable "operator_access" {
  description = "Optional temporary operator path; exact public IPv4 /32 allowlist only"
  type        = object({ compartment_id = string, client_cidrs = set(string) })
  default     = null
  validation {
    condition     = var.operator_access == null ? true : (length(var.operator_access.client_cidrs) > 0 && alltrue([for c in var.operator_access.client_cidrs : can(cidrhost(c, 0)) && can(regex("^[0-9.]+/32$", c))]))
    error_message = "Operator access requires at least one exact IPv4 /32."
  }
}
resource "oci_bastion_bastion" "operator" {
  count                        = var.operator_access == null ? 0 : 1
  bastion_type                 = "STANDARD"
  compartment_id               = var.operator_access.compartment_id
  target_subnet_id             = var.private_subnet_id
  client_cidr_block_allow_list = var.operator_access.client_cidrs
  name                         = "launchpadokeoperator"
  max_session_ttl_in_seconds   = 3600
}
output "bastion_id" { value = try(oci_bastion_bastion.operator[0].id, null) }
