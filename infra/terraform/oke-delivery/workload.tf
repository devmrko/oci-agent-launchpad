variable "workload" {
  type    = object({ home_region = string, compartment_id = string, namespace = string, service_account = string, chat_model = string, embedding_model = string })
  default = null
  validation {
    condition     = var.workload == null ? true : alltrue([for value in [var.workload.namespace, var.workload.service_account, var.workload.chat_model, var.workload.embedding_model] : can(regex("^[a-zA-Z0-9._-]+$", value))])
    error_message = "Workload names and model identifiers must be literal identifiers."
  }
}
provider "oci" {
  alias  = "home"
  region = var.workload == null ? var.region : var.workload.home_region
}
locals {
  workload_condition = var.workload == null ? "" : "request.principal.type='workload', request.principal.cluster_id='${var.cluster_id}', request.principal.namespace='${var.workload.namespace}', request.principal.service_account='${var.workload.service_account}'"
}
resource "oci_identity_policy" "workload" {
  count          = var.workload == null ? 0 : 1
  provider       = oci.home
  compartment_id = var.workload.compartment_id
  name           = "${var.name}-workload"
  description    = "Only the selected OKE workload may call its chat and embedding models"
  statements = [
    "Allow any-user to use generative-ai-chat in compartment id ${var.workload.compartment_id} where all {${local.workload_condition}, target.model.id='${var.workload.chat_model}'}",
    "Allow any-user to use generative-ai-text-embedding in compartment id ${var.workload.compartment_id} where all {${local.workload_condition}, target.model.id='${var.workload.embedding_model}'}"
  ]
}
