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

run "restricted_private_peer" {
  command = apply
  variables {
    private_peer = {
      gateway_id = "ocid1.localpeeringgateway.oc1.test"
      destination_cidrs = ["10.78.1.46/32", "10.78.1.99/32"]
      operator_cidr = "10.78.1.99/32"
    }
  }
  assert {
    condition = length(oci_core_route_table.private.route_rules) == 4
    error_message = "Preserve NAT and service routes alongside the two peer destinations."
  }
  assert {
    condition = length([for r in oci_core_security_list.api.ingress_security_rules : r if r.source == "10.78.1.99/32" && r.tcp_options[0].min == 6443 && r.tcp_options[0].max == 6443]) == 1
    error_message = "Operator access must be exact IP and API port."
  }
  assert {
    condition = strcontains(base64decode(oci_containerengine_node_pool.app.node_metadata.user_data), "/usr/libexec/oci-growfs -y") && strcontains(base64decode(oci_containerengine_node_pool.app.node_metadata.user_data), "73014444032")
    error_message = "New nodes must grow and verify the 68 GiB root budget before joining."
  }
}
run "reject_broad_operator_peer" {
  command = plan
  variables {
    private_peer = { gateway_id = "test", destination_cidrs = ["10.78.1.46/32"], operator_cidr = "0.0.0.0/0" }
  }
  expect_failures = [var.private_peer]
}
