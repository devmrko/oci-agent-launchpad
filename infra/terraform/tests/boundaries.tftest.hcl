mock_provider "oci" {}
variables {
  region              = "ap-seoul-1"
  compartment_id      = "ocid1.compartment.oc1..test"
  availability_domain = "test:AP-SEOUL-1-AD-1"
  image_id            = "ocid1.image.oc1.ap-seoul-1.test"
  ssh_public_key      = "ssh-ed25519 synthetic-test-public-key"
  ssh_source_cidr     = "192.0.2.1/32"
  enable_memory       = false
}
run "without_memory" {
  command = plan
  assert {
    condition = oci_core_instance.runtime.instance_options[0].are_legacy_imds_endpoints_disabled == true
    error_message = "New VMs must disable legacy IMDS endpoints."
  }
  assert {
    condition     = length(oci_database_autonomous_database.memory) == 0
    error_message = "Disabling memory must not create a paid ADB."
  }
}
run "deny_public_ssh" {
  command = plan
  variables { ssh_source_cidr = "0.0.0.0/0" }
  expect_failures = [var.ssh_source_cidr]
}
run "memory_requires_vault_secret" {
  command = plan
  variables { enable_memory = true }
  expect_failures = [oci_database_autonomous_database.memory]
}
run "runtime_bootstrap_uses_references" {
  command = plan
  variables {
    runtime_bootstrap = {
      artifact_id = "ocid1.genericartifact.oc1.test"
      artifact_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      runtime_secret_id = "ocid1.vaultsecret.oc1.test"
      release_alias = "memory-0.4.1"
      app_version = "0.4.1"
      manifest_sha256 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      model_region = "us-ashburn-1"
      chat_model = "google.gemini-2.5-flash-lite"
      embedding_model = "cohere.embed-v4.0"
    }
  }
  assert {
    condition = length(oci_identity_policy.bootstrap) == 1 && length(local.bootstrap_files) == 7
    error_message = "Bootstrap requires helper files, non-secret configuration and an exact-principal policy."
  }
  assert {
    condition = !contains(keys(local.bootstrap_configuration), "password") && length(oci_database_autonomous_database.memory) == 0
    error_message = "An existing runtime secret must not require creating another ADB or embedding passwords."
  }
}
