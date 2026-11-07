terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    oci = { source = "oracle/oci", version = "8.29.0" }
  }
}
provider "oci" { region = var.region }
provider "oci" {
  alias  = "home"
  region = var.home_region
}
variable "region" { type = string }
variable "home_region" { type = string }
variable "compartment_id" { type = string }
variable "project_id" { type = string }
variable "pipeline_id" { type = string }
variable "build_stage_id" { type = string }
variable "artifact_version" { type = string }
variable "existing_policy_name" { type = string }
variable "existing_policy_description" { type = string }
variable "existing_policy_statements" { type = list(string) }
variable "existing_policy_defined_tags" { type = map(string) }
variable "existing_policy_freeform_tags" { type = map(string) }
resource "oci_artifacts_repository" "builds" {
  compartment_id  = var.compartment_id
  display_name    = "launchpad-managed-build-results"
  repository_type = "GENERIC"
  is_immutable    = true
  lifecycle { prevent_destroy = true }
}
locals {
  artifacts = { "launchpad-release" = "release.zip", "launchpad-release-metadata" = "release.json" }
  principal = "request.principal.type = 'devopsbuildpipeline', request.principal.id = '${var.pipeline_id}'"
}
resource "oci_devops_deploy_artifact" "result" {
  for_each                   = local.artifacts
  project_id                 = var.project_id
  display_name               = "managed-${each.key}"
  deploy_artifact_type       = "GENERIC_FILE"
  argument_substitution_mode = "NONE"
  deploy_artifact_source {
    deploy_artifact_source_type = "GENERIC_ARTIFACT"
    repository_id               = oci_artifacts_repository.builds.id
    deploy_artifact_path        = each.value
    deploy_artifact_version     = var.artifact_version
  }
}
# Import the original SDK-created source-read policy; preserve its statements.
resource "oci_identity_policy" "build" {
  provider       = oci.home
  compartment_id = var.compartment_id
  name           = var.existing_policy_name
  description    = var.existing_policy_description
  defined_tags   = var.existing_policy_defined_tags
  freeform_tags  = var.existing_policy_freeform_tags
  statements = concat(var.existing_policy_statements, [
    "Allow any-user to read artifact-repositories in compartment id ${var.compartment_id} where ALL {${local.principal}}",
    "Allow any-user to manage generic-artifacts in compartment id ${var.compartment_id} where ALL {${local.principal}, ANY {request.permission = 'GENERIC_ARTIFACT_CREATE', request.permission = 'GENERIC_ARTIFACT_READ', request.permission = 'GENERIC_ARTIFACT_INSPECT'}}",
    "Allow any-user to read devops-family in compartment id ${var.compartment_id} where ALL {${local.principal}}"
  ])
}
resource "oci_devops_build_pipeline_stage" "deliver" {
  build_pipeline_id         = var.pipeline_id
  build_pipeline_stage_type = "DELIVER_ARTIFACT"
  display_name              = "store-verified-release"
  build_pipeline_stage_predecessor_collection {
    items { id = var.build_stage_id }
  }
  deliver_artifact_collection {
    dynamic "items" {
      for_each = local.artifacts
      content {
        artifact_id   = oci_devops_deploy_artifact.result[items.key].id
        artifact_name = items.key
      }
    }
  }
  depends_on = [oci_identity_policy.build]
}
output "repository_id" { value = oci_artifacts_repository.builds.id }
output "artifact_version" { value = var.artifact_version }
