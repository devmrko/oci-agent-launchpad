variable "manifest_files" {
  type    = list(string)
  default = []
}
resource "oci_devops_deploy_artifact" "manifest" {
  for_each                   = { for index, path in var.manifest_files : format("%02d", index) => path }
  project_id                 = var.project_id
  display_name               = "${var.name}-${each.key}"
  deploy_artifact_type       = "KUBERNETES_MANIFEST"
  argument_substitution_mode = "NONE"
  deploy_artifact_source {
    deploy_artifact_source_type = "INLINE"
    # INLINE is []byte in provider 8.29.0; SDK performs wire base64 encoding.
    base64encoded_content = file(each.value)
  }
}
resource "oci_devops_deploy_stage" "app" {
  count                                   = length(var.manifest_files) == 0 ? 0 : 1
  deploy_stage_type                       = "OKE_DEPLOYMENT"
  deploy_pipeline_id                      = oci_devops_deploy_pipeline.oke.id
  display_name                            = "deploy-service-desk"
  oke_cluster_deploy_environment_id       = oci_devops_deploy_environment.oke.id
  namespace                               = var.workload.namespace
  kubernetes_manifest_deploy_artifact_ids = [for key in sort(keys(oci_devops_deploy_artifact.manifest)) : oci_devops_deploy_artifact.manifest[key].id]
  deploy_stage_predecessor_collection {
    items { id = oci_devops_deploy_pipeline.oke.id }
  }
}
resource "oci_identity_policy" "deployment" {
  count          = length(var.manifest_files) == 0 ? 0 : 1
  provider       = oci.home
  compartment_id = var.workload.compartment_id
  name           = "${var.name}-deployment"
  description    = "Dedicated deployment pipeline access to one OKE cluster and project artifacts"
  statements = [
    "Allow any-user to read subnets in compartment id ${var.workload.compartment_id} where all {request.principal.type='devopsdeploypipeline', request.principal.id='${oci_devops_deploy_pipeline.oke.id}', request.operation='GetSubnet'}",
    "Allow any-user to manage clusters in compartment id ${var.workload.compartment_id} where all {request.principal.type='devopsdeploypipeline', request.principal.id='${oci_devops_deploy_pipeline.oke.id}', target.cluster.id='${var.cluster_id}'}",
    "Allow any-user to read devops-deploy-artifact in compartment id ${var.workload.compartment_id} where all {request.principal.type='devopsdeploypipeline', request.principal.id='${oci_devops_deploy_pipeline.oke.id}', target.project.id='${var.project_id}'}"
  ]
}
