terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    oci = { source = "oracle/oci", version = "8.29.0" }
  }
}
provider "oci" {
  region              = var.region
  config_file_profile = var.profile
}
variable "profile" {
  type    = string
  default = "DEFAULT"
}
variable "region" { type = string }
variable "compartment_id" { type = string }
variable "name" { type = string }
variable "vcn_cidr" {
  type = string
  validation {
    condition     = can(cidrhost(var.vcn_cidr, 1)) && can(regex("^[0-9.]+/16$", var.vcn_cidr)) && !contains(["10.244.0.0/16", "10.96.0.0/16"], var.vcn_cidr)
    error_message = "Use an IPv4 /16 distinct from the Pod and Service CIDRs."
  }
}
variable "kubernetes_version" { type = string }
variable "node_image_id" { type = string }
variable "availability_domain" { type = string }
variable "node_shape" { type = string }
variable "node_ocpus" { type = number }
variable "node_memory_gb" { type = number }
variable "node_count" {
  type = number
  validation {
    condition     = var.node_count >= 1 && floor(var.node_count) == var.node_count
    error_message = "At least one managed node is required."
  }
}
variable "boot_volume_gb" { type = number }
variable "node_capacity" {
  type = object({
    os_gib   = number, images_gib = number, image_update_gib = number,
    logs_gib = number, ephemeral_gib = number, reserve_gib = number
  })
  validation {
    condition     = alltrue([for size in values(var.node_capacity) : size > 0])
    error_message = "Every node disk component needs an explicit positive budget."
  }
}
locals {
  api_cidr     = cidrsubnet(var.vcn_cidr, 8, 0)
  nodes_cidr   = cidrsubnet(var.vcn_cidr, 8, 1)
  required_gib = ceil(sum(values(var.node_capacity)))
  required_gb  = ceil(local.required_gib * 1073741824 / 1000000000)
  all_services = one([for service in data.oci_core_services.regional.services : service if can(regex("All .* Services In Oracle Services Network", service.name))])
}
resource "terraform_data" "capacity" {
  input = var.node_capacity
  lifecycle {
    precondition {
      condition     = var.boot_volume_gb >= local.required_gb
      error_message = "Node boot disk is smaller than OS + images + update + logs + ephemeral + reserve. PVC is separate."
    }
  }
}
data "oci_core_services" "regional" {}
resource "oci_core_vcn" "oke" {
  compartment_id = var.compartment_id
  display_name   = var.name
  cidr_blocks    = [var.vcn_cidr]
  dns_label      = "launchpadoke"
}
resource "oci_core_nat_gateway" "egress" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.oke.id
  display_name   = "${var.name}-nat"
}
resource "oci_core_service_gateway" "oci" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.oke.id
  display_name   = "${var.name}-services"
  services { service_id = local.all_services.id }
}
resource "oci_core_route_table" "private" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.oke.id
  display_name   = "${var.name}-private"
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_nat_gateway.egress.id
  }
  route_rules {
    destination       = local.all_services.cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.oci.id
  }
  dynamic "route_rules" {
    for_each = var.private_peer == null ? toset([]) : var.private_peer.destination_cidrs
    content {
      destination       = route_rules.value
      destination_type  = "CIDR_BLOCK"
      network_entity_id = var.private_peer.gateway_id
    }
  }
}
resource "oci_core_security_list" "api" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.oke.id
  display_name   = "${var.name}-api"
  dynamic "ingress_security_rules" {
    for_each = var.private_peer == null ? [] : [var.private_peer.operator_cidr]
    content {
      protocol = "6"
      source   = ingress_security_rules.value
      tcp_options {
        min = 6443
        max = 6443
      }
    }
  }
  dynamic "ingress_security_rules" {
    for_each = toset([6443, 12250])
    content {
      protocol = "6"
      source   = var.vcn_cidr
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}
resource "oci_core_security_list" "nodes" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.oke.id
  display_name   = "${var.name}-nodes"
  ingress_security_rules {
    protocol = "all"
    source   = local.nodes_cidr
  }
  ingress_security_rules {
    protocol = "6"
    source   = local.api_cidr
    tcp_options {
      min = 10250
      max = 10250
    }
  }
  ingress_security_rules {
    protocol = "1"
    source   = var.vcn_cidr
    icmp_options {
      type = 3
      code = 4
    }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}
resource "oci_core_subnet" "api" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.oke.id
  display_name               = "${var.name}-api"
  cidr_block                 = local.api_cidr
  dns_label                  = "api"
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.private.id
  security_list_ids          = [oci_core_security_list.api.id]
}
resource "oci_core_subnet" "nodes" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.oke.id
  display_name               = "${var.name}-nodes"
  cidr_block                 = local.nodes_cidr
  dns_label                  = "nodes"
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.private.id
  security_list_ids          = [oci_core_security_list.nodes.id]
}
resource "oci_containerengine_cluster" "app" {
  compartment_id     = var.compartment_id
  name               = var.name
  kubernetes_version = var.kubernetes_version
  vcn_id             = oci_core_vcn.oke.id
  type               = "ENHANCED_CLUSTER"
  cluster_pod_network_options { cni_type = "FLANNEL_OVERLAY" }
  endpoint_config {
    is_public_ip_enabled = false
    subnet_id            = oci_core_subnet.api.id
  }
  options {
    kubernetes_network_config {
      pods_cidr     = "10.244.0.0/16"
      services_cidr = "10.96.0.0/16"
    }
  }
}
resource "oci_containerengine_node_pool" "app" {
  depends_on         = [terraform_data.capacity]
  compartment_id     = var.compartment_id
  cluster_id         = oci_containerengine_cluster.app.id
  name               = "${var.name}-nodes"
  kubernetes_version = var.kubernetes_version
  node_shape         = var.node_shape
  node_metadata = {
    user_data = base64encode(templatefile("${path.module}/node-init.sh.tftpl", {
      required_root_bytes = local.required_gib * 1073741824
    }))
  }
  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gb
  }
  node_source_details {
    source_type             = "IMAGE"
    image_id                = var.node_image_id
    boot_volume_size_in_gbs = var.boot_volume_gb
  }
  node_config_details {
    size = var.node_count
    placement_configs {
      availability_domain = var.availability_domain
      subnet_id           = oci_core_subnet.nodes.id
    }
    node_pool_pod_network_option_details { cni_type = "FLANNEL_OVERLAY" }
  }
}
output "cluster_id" { value = oci_containerengine_cluster.app.id }
output "node_pool_id" { value = oci_containerengine_node_pool.app.id }
output "vcn_id" { value = oci_core_vcn.oke.id }
output "private_api_subnet_id" { value = oci_core_subnet.api.id }
output "node_subnet_id" { value = oci_core_subnet.nodes.id }
output "nat_public_ip" { value = oci_core_nat_gateway.egress.nat_ip }
output "capacity_requirement" { value = { filesystem_gib = local.required_gib, volume_gb = local.required_gb } }
