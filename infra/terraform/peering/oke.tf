variable "oke_peer" {
  type    = object({ vcn_id = string, nodes_cidr = string, api_cidr = string })
  default = null
}
resource "oci_core_local_peering_gateway" "observability_oke" {
  count          = var.oke_peer == null ? 0 : 1
  compartment_id = var.compartment_id
  vcn_id         = var.observability_vcn_id
  display_name   = "launchpad-observability-oke-peer"
}
resource "oci_core_local_peering_gateway" "oke" {
  count          = var.oke_peer == null ? 0 : 1
  compartment_id = var.compartment_id
  vcn_id         = var.oke_peer.vcn_id
  display_name   = "launchpad-oke-observability-peer"
  peer_id        = oci_core_local_peering_gateway.observability_oke[0].id
}
output "oke_gateway_id" { value = try(oci_core_local_peering_gateway.oke[0].id, null) }
