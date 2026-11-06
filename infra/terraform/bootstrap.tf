variable "home_region" {
  type        = string
  default     = "us-ashburn-1"
  description = "Tenancy home region for instance-principal policies"
}
variable "runtime_bootstrap" {
  description = "Optional first-boot package and runtime secret references; never secret values"
  type = object({
    artifact_id       = string
    artifact_sha256   = string
    runtime_secret_id = string
    release_alias     = string
    app_version       = string
    manifest_sha256   = string
    model_region      = string
    chat_model        = string
    embedding_model   = string
  })
  default = null
  validation {
    condition     = var.runtime_bootstrap == null ? true : can(regex("^[a-f0-9]{64}$", var.runtime_bootstrap.artifact_sha256)) && can(regex("^[a-f0-9]{64}$", var.runtime_bootstrap.manifest_sha256)) && startswith(var.runtime_bootstrap.runtime_secret_id, "ocid1.vaultsecret.") && startswith(var.runtime_bootstrap.artifact_id, "ocid1.genericartifact.") && can(regex("^[A-Za-z0-9_-][A-Za-z0-9_.-]*$", var.runtime_bootstrap.release_alias))
    error_message = "First boot requires valid artifact/secret OCIDs, SHA-256 values and a safe release alias."
  }
}
provider "oci" {
  alias               = "home"
  region              = var.home_region
  config_file_profile = var.profile
}
locals {
  bootstrap_configuration = var.runtime_bootstrap == null ? {} : merge(var.runtime_bootstrap, { region = var.region, compartment_id = var.compartment_id })
  bootstrap_files = var.runtime_bootstrap == null ? [] : concat([
    for name in ["activate_release.py", "install_release.py", "bootstrap_release.py", "bootstrap_runtime.py", "publish_runtime_secret.py"] : {
      path        = "/opt/launchpad-bootstrap/lib/${name}"
      owner       = "root:root"
      permissions = "0644"
      content     = file("${path.module}/../../deploy/${name}")
      }], [{
      path        = "/etc/launchpad-bootstrap.json"
      owner       = "root:root"
      permissions = "0600"
      content     = jsonencode(local.bootstrap_configuration)
      }, {
      path        = "/etc/systemd/system/launchpad-bootstrap.service"
      owner       = "root:root"
      permissions = "0644"
      content     = <<-UNIT
        [Unit]
        Description=Launchpad first boot
        After=network-online.target
        Wants=network-online.target
        StartLimitIntervalSec=0
        [Service]
        Type=oneshot
        ExecStart=/opt/launchpad-bootstrap/venv/bin/python /opt/launchpad-bootstrap/lib/bootstrap_runtime.py
        RemainAfterExit=yes
        Restart=on-failure
        RestartSec=30
        TimeoutStartSec=900
        UMask=0077
        [Install]
        WantedBy=multi-user.target
      UNIT
  }])
  bootstrap_commands = var.runtime_bootstrap == null ? [] : [
    ["python3.12", "-m", "venv", "/opt/launchpad-bootstrap/venv"],
    ["/opt/launchpad-bootstrap/venv/bin/pip", "install", "oci==2.188.0"],
    ["systemctl", "daemon-reload"],
    ["systemctl", "enable", "--now", "--no-block", "launchpad-bootstrap.service"]
  ]
  cloud_config = { packages = var.bootstrap_packages, write_files = local.bootstrap_files, runcmd = local.bootstrap_commands }
}
resource "oci_identity_policy" "bootstrap" {
  count          = var.runtime_bootstrap == null ? 0 : 1
  provider       = oci.home
  compartment_id = var.compartment_id
  name           = "${var.name}-bootstrap"
  description    = "Exact first-boot VM principal and runtime secret; no ADMIN access"
  statements = [
    "Allow any-user to read secret-bundles in compartment id ${var.compartment_id} where ALL {request.principal.id = '${oci_core_instance.runtime.id}', target.secret.id = '${var.runtime_bootstrap.runtime_secret_id}'}",
    "Allow any-user to read generic-artifacts in compartment id ${var.compartment_id} where request.principal.id = '${oci_core_instance.runtime.id}'",
    "Allow any-user to use generative-ai-chat in compartment id ${var.compartment_id} where ALL {request.principal.id = '${oci_core_instance.runtime.id}', target.model.id = '${var.runtime_bootstrap.chat_model}'}",
    "Allow any-user to use generative-ai-text-embedding in compartment id ${var.compartment_id} where ALL {request.principal.id = '${oci_core_instance.runtime.id}', target.model.id = '${var.runtime_bootstrap.embedding_model}'}"
  ]
}
