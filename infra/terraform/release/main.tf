locals {
  deployment_spec = yamlencode({
    version          = "1.0"
    component        = "deployment"
    timeoutInSeconds = 900
    files            = [{ source = "/", destination = "${var.staging_root}/${var.release_alias}" }]
    steps = [{ stepType = "Command", name = "Verify install and activate", timeoutInSeconds = 720,
    command = "set -eu\nsudo -n /usr/local/sbin/launchpad-deploy ${var.release_alias}" }]
  })
}
terraform {
  required_version = ">= 1.7, < 2.0"
  required_providers {
    oci = { source = "oracle/oci", version = "~> 8.9" }
  }
}
provider "oci" {
  region              = var.region
  config_file_profile = var.profile
}
provider "oci" {
  alias               = "home"
  region              = var.home_region
  config_file_profile = var.profile
}
data "oci_devops_project" "target" { project_id = var.project_id }
resource "oci_devops_deploy_environment" "target" {
  project_id              = var.project_id
  display_name            = "${var.name}-${var.release_alias}-vm"
  deploy_environment_type = "COMPUTE_INSTANCE_GROUP"
  compute_instance_group_selectors {
    items {
      selector_type        = "INSTANCE_IDS"
      compute_instance_ids = [var.instance_id]
    }
  }
}
data "oci_core_instance" "target" { instance_id = var.instance_id }
resource "oci_artifacts_repository" "releases" {
  compartment_id  = var.compartment_id
  display_name    = "${var.name}-packages"
  repository_type = "GENERIC"
  is_immutable    = true
  lifecycle { prevent_destroy = true }
}
resource "oci_generic_artifacts_content_artifact_by_path" "bundle" {
  repository_id = oci_artifacts_repository.releases.id
  artifact_path = "${var.release_alias}/release.zip"
  version       = var.app_version
  source        = var.bundle_path
  lifecycle {
    prevent_destroy = true
    # OCI 8.29 reads content back as a hash even when source is used.
    ignore_changes = [content]
    postcondition {
      condition     = self.sha256 == var.bundle_sha256
      error_message = "Uploaded artifact checksum differs from approved package."
    }
    precondition {
      condition     = filesha256(var.bundle_path) == var.bundle_sha256
      error_message = "Bundle checksum does not match the approved release."
    }
  }
}
resource "oci_devops_deploy_pipeline" "release" {
  project_id   = var.project_id
  display_name = "${var.name}-${var.release_alias}"
  description  = "Verified offline package install and activation"
}
resource "oci_devops_deploy_artifact" "bundle" {
  project_id                 = var.project_id
  display_name               = "${var.release_alias}-package"
  deploy_artifact_type       = "GENERIC_FILE"
  argument_substitution_mode = "NONE"
  deploy_artifact_source {
    deploy_artifact_source_type = "GENERIC_ARTIFACT"
    repository_id               = oci_artifacts_repository.releases.id
    deploy_artifact_path        = oci_generic_artifacts_content_artifact_by_path.bundle.artifact_path
    deploy_artifact_version     = oci_generic_artifacts_content_artifact_by_path.bundle.version
  }
}
resource "oci_devops_deploy_artifact" "spec" {
  project_id                 = var.project_id
  display_name               = "${var.release_alias}-install"
  deploy_artifact_type       = "DEPLOYMENT_SPEC"
  argument_substitution_mode = "NONE"
  deploy_artifact_source {
    deploy_artifact_source_type = "INLINE"
    base64encoded_content       = base64encode(local.deployment_spec)
  }
  lifecycle {
    # OCI reads inline content back decoded; compare actual semantics below.
    ignore_changes = [deploy_artifact_source[0].base64encoded_content]
    postcondition {
      condition     = try(yamldecode(self.deploy_artifact_source[0].base64encoded_content) == yamldecode(local.deployment_spec), false) || try(yamldecode(base64decode(self.deploy_artifact_source[0].base64encoded_content)) == yamldecode(local.deployment_spec), false)
      error_message = "Stored deployment specification differs from this immutable release."
    }
  }
}
resource "oci_devops_deploy_stage" "release" {
  deploy_pipeline_id                           = oci_devops_deploy_pipeline.release.id
  display_name                                 = "Install ${var.release_alias}"
  deploy_stage_type                            = "COMPUTE_INSTANCE_GROUP_ROLLING_DEPLOYMENT"
  compute_instance_group_deploy_environment_id = oci_devops_deploy_environment.target.id
  deployment_spec_deploy_artifact_id           = oci_devops_deploy_artifact.spec.id
  deploy_artifact_ids                          = [oci_devops_deploy_artifact.bundle.id]
  deploy_stage_predecessor_collection {
    items { id = oci_devops_deploy_pipeline.release.id }
  }
  rollout_policy {
    policy_type            = "COMPUTE_INSTANCE_GROUP_LINEAR_ROLLOUT_POLICY_BY_COUNT"
    batch_count            = 1
    batch_delay_in_seconds = 1
  }
  lifecycle {
    precondition {
      condition     = data.oci_devops_project.target.compartment_id == var.compartment_id && data.oci_core_instance.target.compartment_id == var.compartment_id
      error_message = "Project, environment and VM must belong to the selected compartment."
    }

  }
}
resource "oci_identity_policy" "release" {
  provider       = oci.home
  compartment_id = var.compartment_id
  name           = "${var.name}-${var.release_alias}-deployment"
  description    = "Exact deployment pipeline and VM principals; no secret access"
  statements = concat([
    for permission in ["read devops-family", "read instance-family", "use instance-agent-command-family", "use ons-topics", "read generic-artifacts", "read artifact-repositories"] :
    "Allow any-user to ${permission} in compartment id ${var.compartment_id} where request.principal.id = '${oci_devops_deploy_pipeline.release.id}'"
    ], [
    for permission in ["use instance-agent-command-execution-family", "read generic-artifacts"] :
    "Allow any-user to ${permission} in compartment id ${var.compartment_id} where request.principal.id = '${var.instance_id}'"
  ])
}
output "pipeline_id" { value = oci_devops_deploy_pipeline.release.id }
output "repository_id" { value = oci_artifacts_repository.releases.id }
output "artifact_id" { value = oci_generic_artifacts_content_artifact_by_path.bundle.artifact_id }
output "manifest_sha256" { value = var.manifest_sha256 }
output "bootstrap_release" {
  value = { directory = var.release_alias, version = var.app_version, manifest_sha256 = var.manifest_sha256 }
}
