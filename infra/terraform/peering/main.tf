terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    oci = { source = "oracle/oci", version = "8.29.0" }
  }
}
provider "oci" { region = var.region }
variable "region" { type = string }
variable "compartment_id" { type = string }
variable "app_vcn_id" { type = string }
variable "observability_vcn_id" { type = string }
variable "app_client_cidr" { type = string }
variable "lb_cidr" { type = string }
variable "existing_route_name" { type = string }
variable "existing_route_tags" { type = map(string) }
variable "existing_route_defined_tags" { type = map(string) }
variable "existing_routes" {
  type = list(object({ destination = string, destination_type = string, network_entity_id = string }))
}
resource "oci_core_local_peering_gateway" "observability" {
  compartment_id = var.compartment_id
  vcn_id         = var.observability_vcn_id
  display_name   = "launchpad-observability-peer"
}
resource "oci_core_local_peering_gateway" "app" {
  compartment_id = var.compartment_id
  vcn_id         = var.app_vcn_id
  display_name   = "launchpad-app-peer"
  peer_id        = oci_core_local_peering_gateway.observability.id
}
# Import the SDK-created route table before applying. App routing stays in its owner state.
resource "oci_core_route_table" "observability" {
  compartment_id = var.compartment_id
  vcn_id         = var.observability_vcn_id
  display_name   = var.existing_route_name
  freeform_tags  = var.existing_route_tags
  defined_tags   = var.existing_route_defined_tags
  dynamic "route_rules" {
    for_each = var.existing_routes
    content {
      destination       = route_rules.value.destination
      destination_type  = route_rules.value.destination_type
      network_entity_id = route_rules.value.network_entity_id
    }
  }
  route_rules {
    destination       = var.app_client_cidr
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_local_peering_gateway.observability.id
  }
  dynamic "route_rules" {
    for_each = var.oke_peer == null ? [] : [var.oke_peer.nodes_cidr, var.oke_peer.api_cidr]
    content {
      destination       = route_rules.value
      destination_type  = "CIDR_BLOCK"
      network_entity_id = oci_core_local_peering_gateway.observability_oke[0].id
    }
  }
  lifecycle { prevent_destroy = true }
}
output "app_route" {
  value = { destination = var.lb_cidr, gateway_id = oci_core_local_peering_gateway.app.id }
}
output "peer_status" { value = oci_core_local_peering_gateway.app.peering_status }
