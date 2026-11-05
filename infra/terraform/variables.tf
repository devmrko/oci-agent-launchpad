variable "region" {
  type        = string
  description = "OCI region"
}
variable "compartment_id" {
  type        = string
  description = "Target compartment OCID"
}
variable "availability_domain" {
  type        = string
  description = "Availability domain name"
}
variable "image_id" {
  type        = string
  description = "Oracle Linux platform or compatible custom image OCID"
}
variable "ssh_public_key" {
  type        = string
  description = "SSH public key contents; never a private key"
}
variable "ssh_source_cidr" {
  type        = string
  description = "Administrator public IPv4 /32"
  validation {
    condition     = can(cidrnetmask(var.ssh_source_cidr)) && endswith(var.ssh_source_cidr, "/32")
    error_message = "Use one administrator IPv4 address with /32."
  }
}
variable "name" {
  type        = string
  description = "Resource name prefix"
  default     = "oci-agent-launchpad"
}
variable "profile" {
  type        = string
  description = "Local OCI config profile"
  default     = "DEFAULT"
}
variable "vcn_cidr" {
  type        = string
  description = "Non-overlapping VCN CIDR"
  default     = "10.78.0.0/16"
}
variable "subnet_cidr" {
  type        = string
  description = "Subnet CIDR inside VCN"
  default     = "10.78.1.0/24"
}
variable "vm_shape" {
  type        = string
  description = "Flexible x86 VM shape matching image"
  default     = "VM.Standard.E5.Flex"
}
variable "vm_ocpus" {
  type        = number
  description = "VM OCPUs"
  default     = 1
}
variable "vm_memory_gb" {
  type        = number
  description = "VM memory GB"
  default     = 8
}
variable "boot_volume_gb" {
  type        = number
  description = "Boot volume GB"
  default     = 50
}
variable "enable_memory" {
  type        = bool
  description = "Create dedicated paid ADB"
  default     = true
}
variable "adb_name" {
  type        = string
  description = "Unique ADB database name"
  default     = "LPMEMORY"
}
variable "adb_version" {
  type        = string
  description = "Region-supported Agent Memory compatible DB version"
  default     = "26ai"
}
variable "adb_ecpus" {
  type        = number
  description = "ADB ECPUs"
  default     = 2
  validation {
    condition     = var.adb_ecpus >= 2
    error_message = "Standalone ECPU ADB requires at least 2 ECPUs."
  }
}
variable "adb_storage_gb" {
  type        = number
  description = "ADB storage GB"
  default     = 20
}
variable "adb_admin_secret_id" {
  type        = string
  description = "Existing OCI Vault password secret OCID; conditional when memory enabled"
  default     = null
}
variable "bootstrap_packages" {
  type        = list(string)
  description = "OS packages; custom images may pass []"
  default     = ["python3.12", "python3.12-pip"]
}
