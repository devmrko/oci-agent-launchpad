mock_provider "oci" {
  mock_data "oci_core_services" {
    defaults = { services = [{ id = "service", name = "All ICN Services In Oracle Services Network", cidr_block = "all-icn-services-in-oracle-services-network" }] }
  }
}
variables {
  region              = "ap-seoul-1"
  compartment_id      = "ocid1.compartment.oc1..test"
  name                = "test-oke"
  vcn_cidr            = "10.80.0.0/16"
  kubernetes_version  = "v1.34.10"
  node_image_id       = "ocid1.image.oc1.test"
  availability_domain = "test:AP-SEOUL-1-AD-1"
  node_shape          = "VM.Standard.E5.Flex"
  node_ocpus          = 2
  node_memory_gb      = 16
  node_count          = 1
  boot_volume_gb      = 100
  node_capacity       = { os_gib = 20, images_gib = 8, image_update_gib = 8, logs_gib = 8, ephemeral_gib = 8, reserve_gib = 16 }
}
run "private_cluster_with_separate_capacity" {
  command = plan
  assert {
    condition     = oci_containerengine_cluster.app.type == "ENHANCED_CLUSTER" && oci_containerengine_cluster.app.endpoint_config[0].is_public_ip_enabled == false
    error_message = "Workload identity cluster must keep its API private."
  }
  assert {
    condition     = oci_core_subnet.api.prohibit_public_ip_on_vnic && oci_core_subnet.nodes.prohibit_public_ip_on_vnic
    error_message = "API and nodes must not receive public addresses."
  }
  assert {
    condition     = output.capacity_requirement.filesystem_gib == 68 && output.capacity_requirement.volume_gb == 74
    error_message = "All node disk components and GiB-to-GB conversion must be counted."
  }
  assert {
    condition     = alltrue([for rule in oci_core_security_list.api.ingress_security_rules : rule.source != "0.0.0.0/0"])
    error_message = "API ingress must remain internal."
  }
}
run "reject_insufficient_node_disk" {
  command = plan
  variables { boot_volume_gb = 50 }
  expect_failures = [terraform_data.capacity]
}
run "reject_no_nodes" {
  command = plan
  variables { node_count = 0 }
  expect_failures = [var.node_count]
}
run "reject_pod_network_collision" {
  command = plan
  variables { vcn_cidr = "10.244.0.0/16" }
  expect_failures = [var.vcn_cidr]
}
