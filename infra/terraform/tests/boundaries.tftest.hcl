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
