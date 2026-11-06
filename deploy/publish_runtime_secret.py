"""Publish only the app's runtime memory configuration to OCI Vault via stdin."""

import argparse
import base64
import json
import uuid

import oci

ALLOWED = {
    "dsn",
    "user",
    "password",
    "schema_owner",
    "store_id",
    "compartment",
    "embedding_region",
    "embedding_model",
    "embedding_dimensions",
    "namespace",
}


def validate_runtime(value):
    if not isinstance(value, dict) or set(value) - ALLOWED:
        raise ValueError("Only runtime memory settings are allowed")
    for key in ["dsn", "user", "password", "schema_owner", "store_id", "compartment"]:
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError("Missing runtime setting: " + key)
    if value["user"].upper() in {
        "ADMIN",
        "SYS",
        "SYSTEM",
        value["schema_owner"].upper(),
    }:
        raise ValueError(
            "Runtime credential must not be an administrator or schema owner"
        )
    return value


def publish(client, reader, compartment, vault, key, name, runtime):
    payload = json.dumps(validate_runtime(runtime), sort_keys=True).encode()
    matches = [
        s
        for s in oci.pagination.list_call_get_all_results(
            client.list_secrets, compartment_id=compartment, vault_id=vault
        ).data
        if s.secret_name == name and s.lifecycle_state != "DELETED"
    ]
    if matches:
        secret = matches[0]
        if secret.lifecycle_state != "ACTIVE":
            raise ValueError("Existing secret is not active")
        old = reader.get_secret_bundle(
            secret.id, stage="CURRENT"
        ).data.secret_bundle_content.content
        if base64.b64decode(old) != payload:
            raise ValueError(
                "Existing secret differs; use an explicit rotation procedure"
            )
        return secret.id
    return client.create_secret(
        oci.vault.models.CreateSecretDetails(
            compartment_id=compartment,
            vault_id=vault,
            key_id=key,
            secret_name=name,
            description="Launchpad application memory only; no administrator credential",
            secret_content=oci.vault.models.Base64SecretContentDetails(
                content=base64.b64encode(payload).decode()
            ),
        ),
        opc_retry_token=str(uuid.uuid5(uuid.NAMESPACE_URL, vault + name)),
    ).data.id


def main():
    import sys

    p = argparse.ArgumentParser(description=__doc__)
    for name in ["region", "compartment", "vault", "key", "name"]:
        p.add_argument("--" + name, required=True)
    p.add_argument("--profile", default="DEFAULT")
    a = p.parse_args()
    cfg = oci.config.from_file(profile_name=a.profile)
    cfg["region"] = a.region
    identifier = publish(
        oci.vault.VaultsClient(cfg),
        oci.secrets.SecretsClient(cfg),
        a.compartment,
        a.vault,
        a.key,
        a.name,
        json.load(sys.stdin),
    )
    print(json.dumps({"secret_id": identifier}))


if __name__ == "__main__":
    main()
