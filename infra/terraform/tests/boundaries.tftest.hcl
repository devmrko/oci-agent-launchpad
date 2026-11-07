mock_provider "oci" {}
variables {
  region              = "ap-seoul-1"
  compartment_id      = "ocid1.compartment.oc1..test"
  availability_domain = "test:AP-SEOUL-1-AD-1"
  image_id            = "ocid1.image.oc1.ap-seoul-1.test"
  ssh_public_key      = "ssh-ed25519 synthetic-test-public-key"
  ssh_source_cidr     = "192.0.2.1/32"
  enable_memory       = false
  runtime_capacity_plan = {
    schema_version = 1
    role           = "synthetic-runtime"
    reserve_gib    = 5
    components     = [{ name = "stack", phase = "resident", gib = 10, copies = 1, basis = "test fixture" }]
  }
}
run "without_memory" {
  command = plan
  assert {
    condition     = oci_core_instance.runtime.instance_options[0].are_legacy_imds_endpoints_disabled == true
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
      artifact_id       = "ocid1.genericartifact.oc1.test"
      artifact_sha256   = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      runtime_secret_id = "ocid1.vaultsecret.oc1.test"
      release_alias     = "memory-0.4.1"
      app_version       = "0.4.1"
      manifest_sha256   = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      model_region      = "us-ashburn-1"
      chat_model        = "google.gemini-2.5-flash-lite"
      embedding_model   = "cohere.embed-v4.0"
    }
  }
  assert {
    condition     = length(oci_identity_policy.bootstrap) == 1 && length(local.bootstrap_files) == 7
    error_message = "Bootstrap requires helper files, non-secret configuration and an exact-principal policy."
  }
  assert {
    condition     = !contains(keys(local.bootstrap_configuration), "password") && length(oci_database_autonomous_database.memory) == 0
    error_message = "An existing runtime secret must not require creating another ADB or embedding passwords."
  }
}

run "reject_small_boot_volume" {
  command = plan
  variables { boot_volume_gb = 10 }
  expect_failures = [terraform_data.runtime_capacity]
}
run "budget_counts_concurrent_work" {
  command = plan
  variables {
    boot_volume_gb = 100
    runtime_capacity_plan = {
      schema_version = 1
      role           = "synthetic-builder"
      reserve_gib    = 5
      components = [
        { name = "stack", phase = "resident", gib = 10, copies = 1, basis = "test fixture" },
        { name = "images", phase = "growth", gib = 4, copies = 2, basis = "test retention" },
        { name = "build", phase = "transient", gib = 6, copies = 2, basis = "test concurrency" }
      ]
    }
  }
  assert {
    condition     = output.runtime_capacity_requirement.filesystem_gib == 35 && output.runtime_capacity_requirement.volume_gb == 38
    error_message = "All simultaneous copies and reserve must be counted."
  }
}
