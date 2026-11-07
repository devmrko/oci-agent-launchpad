"""Explicit OCI authentication shared by model and embedding clients."""


def inference_client(*, region, auth="instance"):
    import oci

    options = {
        "service_endpoint": f"https://inference.generativeai.{region}.oci.oraclecloud.com",
        "timeout": (5, 25),
        "retry_strategy": oci.retry.NoneRetryStrategy(),
    }
    if auth == "config":
        config = oci.config.from_file()
        config["region"] = region
        return oci.generative_ai_inference.GenerativeAiInferenceClient(config, **options)
    if auth == "instance":
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    elif auth == "oke":
        signer = oci.auth.signers.get_oke_workload_identity_resource_principal_signer()
    else:
        raise ValueError("DESK_OCI_AUTH must be instance, config or oke")
    return oci.generative_ai_inference.GenerativeAiInferenceClient({}, signer=signer, **options)
