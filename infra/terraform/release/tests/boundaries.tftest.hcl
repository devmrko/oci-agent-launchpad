mock_provider "oci" {}
mock_provider "oci" { alias = "home" }
override_data {
  target = data.oci_devops_project.target
  values = { compartment_id = "comp" }
}

override_data {
  target = data.oci_core_instance.target
  values = { compartment_id = "comp" }
}
variables {
  region          = "ap-seoul-1"
  home_region     = "us-ashburn-1"
  compartment_id  = "comp"
  project_id      = "project"
  instance_id     = "vm"
  release_alias   = "memory-0.4.1"
  app_version     = "0.4.1"
  bundle_path     = "tests/package.txt"
  bundle_sha256   = "75bb77250cfbf7c4fe0b9cff53de1f7a014395dfedb177bf01dff72437eb628e"
  manifest_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
run "immutable_and_scoped" {
  command = plan
  assert {
    condition     = oci_artifacts_repository.releases.is_immutable
    error_message = "Release packages must be immutable."
  }
  assert {
    condition     = length(oci_identity_policy.release[0].statements) == 8
    error_message = "Unexpected additional permissions."
  }
}
run "reject_bad_checksum" {
  command = plan
  variables { bundle_sha256 = "0000000000000000000000000000000000000000000000000000000000000000" }
  expect_failures = [oci_generic_artifacts_content_artifact_by_path.bundle]
}
run "reject_shell_alias" {
  command = plan
  variables { release_alias = "bad;id" }
  expect_failures = [var.release_alias]
}
run "reject_other_compartment" {
  command = plan
  override_data {
    target = data.oci_core_instance.target
    values = { compartment_id = "other" }
  }
  expect_failures = [oci_devops_deploy_stage.release]
}

run "reject_wrong_release_metadata" {
  command = plan
  variables { release_metadata_path = "tests/package.txt" }
  expect_failures = [oci_generic_artifacts_content_artifact_by_path.metadata]
}

run "external_policy_owner" {
  command = plan
  variables { create_deployment_policy = false }
  assert {
    condition = length(oci_identity_policy.release) == 0
    error_message = "An externally managed policy must not create another policy."
  }
}
run "exact_additional_principal" {
  command = plan
  variables { additional_pipeline_ids = ["ocid1.devopsdeploypipeline.oc1.ap-seoul-1.test"] }
  assert {
    condition = length(oci_identity_policy.release[0].statements) == 14 && length([for s in slice(oci_identity_policy.release[0].statements, 6, 12) : s if strcontains(s, "request.principal.id = 'ocid1.devopsdeploypipeline.oc1.ap-seoul-1.test'")]) == 6
    error_message = "Additional grants must name the exact pipeline."
  }
}

run "post_check_disabled_preserves_single_step" {
  command = plan
  assert {
    condition = length(yamldecode(local.deployment_spec).steps) == 1 && yamldecode(local.deployment_spec).timeoutInSeconds == 900
    error_message = "Default deployment must preserve the original single step."
  }
}
run "post_check_after_activation" {
  command = plan
  variables { post_deploy_check_command = "/usr/local/sbin/launchpad-check" }
  assert {
    condition = length(yamldecode(local.deployment_spec).steps) == 2 && yamldecode(local.deployment_spec).steps[1].command == "set -eu\nsudo -n /usr/local/sbin/launchpad-check memory-0.4.1" && yamldecode(local.deployment_spec).timeoutInSeconds == 1200
    error_message = "Verifier must follow activation and receive only the pinned alias."
  }
}
run "reject_inline_check_command" {
  command = plan
  variables { post_deploy_check_command = "/usr/local/sbin/check;id" }
  expect_failures = [var.post_deploy_check_command]
}
run "reject_check_timeout" {
  command = plan
  variables { post_deploy_check_timeout_seconds = 601 }
  expect_failures = [var.post_deploy_check_timeout_seconds]
}
