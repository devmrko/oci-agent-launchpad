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
