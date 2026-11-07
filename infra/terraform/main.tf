terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    oci = { source = "oracle/oci", version = "~> 8.9" }
  }
}
provider "oci" {
  region              = var.region
  config_file_profile = var.profile
}
resource "oci_core_vcn" "runtime" {
  compartment_id = var.compartment_id
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.name}-vcn"
}
resource "oci_core_internet_gateway" "runtime" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.runtime.id
  display_name   = "${var.name}-igw"
  enabled        = true
}
resource "oci_core_route_table" "runtime" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.runtime.id
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.runtime.id
  }
}
resource "oci_core_security_list" "runtime" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.runtime.id
  ingress_security_rules {
    protocol = "6"
    source   = var.ssh_source_cidr
    tcp_options {
      min = 22
      max = 22
    }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}
resource "oci_core_subnet" "runtime" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.runtime.id
  cidr_block        = var.subnet_cidr
  route_table_id    = oci_core_route_table.runtime.id
  security_list_ids = [oci_core_security_list.runtime.id]
  display_name      = "${var.name}-subnet"
}
resource "oci_core_instance" "runtime" {
  depends_on = [terraform_data.runtime_capacity]
  compartment_id      = var.compartment_id
  availability_domain = var.availability_domain
  display_name        = "${var.name}-vm"
  shape               = var.vm_shape
  shape_config {
    ocpus         = var.vm_ocpus
    memory_in_gbs = var.vm_memory_gb
  }
  source_details {
    source_type             = "image"
    source_id               = var.image_id
    boot_volume_size_in_gbs = var.boot_volume_gb
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.runtime.id
    assign_public_ip = true
  }
  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }
  agent_config {
    is_management_disabled = false
    is_monitoring_disabled = false
    plugins_config {
      name          = "Compute Instance Run Command"
      desired_state = "ENABLED"
    }
  }
  # First-boot content is immutable for an existing VM. Use release deployment
  # for updates; changing bootstrap source must not replace a data-bearing VM.
  lifecycle {
    ignore_changes = [metadata["user_data"]]
  }
  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64gzip("#cloud-config\n${yamlencode(local.cloud_config)}")
  }
}
resource "oci_database_autonomous_database" "memory" {
  count                               = var.enable_memory ? 1 : 0
  compartment_id                      = var.compartment_id
  display_name                        = "${var.name}-memory"
  db_name                             = var.adb_name
  db_version                          = var.adb_version
  db_workload                         = "OLTP"
  compute_model                       = "ECPU"
  compute_count                       = var.adb_ecpus
  data_storage_size_in_gb             = var.adb_storage_gb
  license_model                       = "LICENSE_INCLUDED"
  is_auto_scaling_enabled             = false
  is_auto_scaling_for_storage_enabled = false
  is_mtls_connection_required         = false
  whitelisted_ips                     = ["${oci_core_instance.runtime.public_ip}/32"]
  secret_id                           = var.adb_admin_secret_id
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.adb_admin_secret_id != null
      error_message = "Memory requires an existing OCI Vault admin-password secret OCID."
    }
  }
}
output "instance_id" { value = oci_core_instance.runtime.id }
output "instance_public_ip" { value = oci_core_instance.runtime.public_ip }
output "memory_adb_id" { value = try(oci_database_autonomous_database.memory[0].id, null) }

output "deployment" {
  description = "Non-secret input for deploy/render_environment.py"
  value = {
    region         = var.region
    compartment_id = var.compartment_id
    instance_id    = oci_core_instance.runtime.id
    public_ip      = oci_core_instance.runtime.public_ip
    memory_adb_id  = try(oci_database_autonomous_database.memory[0].id, null)
  }
}
