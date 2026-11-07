# Required budget for the root filesystem, before provisioning any new VM.
variable "runtime_capacity_plan" {
  description = "Explicit root filesystem peak budget, with measured or estimated evidence. No implicit size default."
  nullable    = false
  type = object({
    schema_version = number
    role           = string
    reserve_gib    = number
    components = list(object({
      name   = string
      phase  = string
      gib    = number
      copies = number
      basis  = string
    }))
  })
  validation {
    condition = var.runtime_capacity_plan.schema_version == 1 && trimspace(var.runtime_capacity_plan.role) != "" && var.runtime_capacity_plan.reserve_gib > 0 && length(var.runtime_capacity_plan.components) > 0 && alltrue([
      for c in var.runtime_capacity_plan.components : trimspace(c.name) != "" && trimspace(c.basis) != "" && contains(["resident", "growth", "transient"], c.phase) && c.gib >= 0 && c.copies >= 1 && floor(c.copies) == c.copies
    ]) && length(distinct([for c in var.runtime_capacity_plan.components : c.name])) == length(var.runtime_capacity_plan.components)
    error_message = "Capacity requires schema 1, a role, positive reserve, and unique nonnegative components with integer copies and evidence."
  }
}
locals {
  runtime_required_filesystem_gib = ceil(sum([for c in var.runtime_capacity_plan.components : c.gib * c.copies]) + var.runtime_capacity_plan.reserve_gib)
  # Conservative decimal GB conversion; guest filesystem is checked separately.
  runtime_required_volume_gb = ceil(local.runtime_required_filesystem_gib * 1073741824 / 1000000000)
}
resource "terraform_data" "runtime_capacity" {
  input = var.runtime_capacity_plan
  lifecycle {
    precondition {
      condition     = var.boot_volume_gb >= local.runtime_required_volume_gb
      error_message = "boot_volume_gb is below the explicit peak capacity budget. Increase provisioned capacity or correct the evidenced plan."
    }
  }
}
output "runtime_capacity_requirement" {
  value = {
    filesystem_gib = local.runtime_required_filesystem_gib
    volume_gb      = local.runtime_required_volume_gb
  }
}
