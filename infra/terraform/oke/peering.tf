variable "private_peer" {
  type    = object({ gateway_id = string, destination_cidrs = set(string), operator_cidr = string })
  default = null
  validation {
    condition     = var.private_peer == null ? true : (can(regex("/32$", var.private_peer.operator_cidr)) && alltrue([for c in var.private_peer.destination_cidrs : can(cidrhost(c, 0)) && can(regex("/32$", c))]))
    error_message = "Peer destinations and operator must be exact IPv4 /32 addresses."
  }
}
