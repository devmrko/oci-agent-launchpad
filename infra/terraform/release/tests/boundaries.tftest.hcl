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
    condition     = length(oci_identity_policy.release.statements) == 8
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
