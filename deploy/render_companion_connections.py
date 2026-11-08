"""Create a fresh Companion configuration bundle; never read tokens or change OCI."""
import argparse
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

SCOPE = ("profile", "tenancy", "user", "region", "compartment")
PREFIX = {"VM": "instance", "ADB": "autonomousdatabase", "OKE": "cluster"}


def text(value, field, limit=255):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value) or "<" in value or ">" in value:
        raise ValueError("Invalid or unresolved field: " + field)
    return value


def ocid(value, kind):
    text(value, kind)
    if not re.fullmatch(r"ocid1\." + kind + r"\.[A-Za-z0-9_.-]+", value):
        raise ValueError("Invalid OCID type: " + kind)
    return value


def absolute(value, field):
    text(value, field, 4096)
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Absolute path without parent traversal required: " + field)
    return value


def identifier(value, field):
    text(value, field)
    if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", value):
        raise ValueError("Invalid name: " + field)
    return value


def keys(obj, allowed, field):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        raise ValueError("Unknown fields in " + field + "; supply references, not credentials")


def render(config):
    keys(config, ("scope", "apps"), "config")
    scope = config["scope"]
    keys(scope, SCOPE, "scope")
    for field in SCOPE:
        text(scope.get(field), field)
    for field, kind in (("tenancy", "tenancy"), ("user", "user"), ("compartment", "compartment")):
        ocid(scope[field], kind)
    identifier(scope["region"], "region")
    apps = config["apps"]
    if not isinstance(apps, list) or not 1 <= len(apps) <= 100:
        raise ValueError("Supply 1 to 100 apps")
    registrations, credentials, workloads = [], [], []
    used_keys, used_ids = set(), set()
    for app in apps:
        keys(app, ("key", "id", "name", "environment", "baseUrl", "tokenFile", "dependencies", "oke"), "app")
        key = identifier(app["key"], "key")
        stable = json.dumps([scope[k] for k in SCOPE] + [key], separators=(",", ":"))
        app_id = str(uuid.UUID(app["id"])) if "id" in app else str(uuid.uuid5(uuid.NAMESPACE_URL, stable))
        if key in used_keys or app_id in used_ids:
            raise ValueError("Duplicate app key or id")
        used_keys.add(key); used_ids.add(app_id)
        name = text(app["name"], "name", 100)
        environment = text(app["environment"], "environment", 80)
        url = urlsplit(text(app["baseUrl"], "baseUrl"))
        if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("Current Companion requires an HTTP loopback tunnel URL")
        token_file = absolute(app["tokenFile"], "tokenFile")
        deps = app.get("dependencies", [])
        if not isinstance(deps, list) or len(deps) > 8:
            raise ValueError("At most 8 dependencies per app")
        seen = set()
        for dep in deps:
            keys(dep, ("type", "label", "ocid"), "dependency")
            if dep["type"] not in PREFIX:
                raise ValueError("Unsupported dependency type")
            ocid(dep["ocid"], PREFIX[dep["type"]]); text(dep["label"], "label", 100)
            if dep["ocid"] in seen:
                raise ValueError("Duplicate dependency")
            seen.add(dep["ocid"])
        credential_id = "app-" + app_id
        registrations.append(dict(scope, id=app_id, name=name, environment=environment, adapter="monitoring-http-v1", baseUrl=app["baseUrl"], credentialRef=credential_id, dependencies=deps))
        credentials.append(dict(scope, id=credential_id, label=name + " authentication", tokenFile=token_file))
        if "oke" in app:
            oke = app["oke"]
            keys(oke, ("clusterId", "kubeconfig", "namespace", "deployment", "server", "tlsServerName", "inspectNodes"), "oke")
            cluster = ocid(oke["clusterId"], "cluster")
            if not any(d["type"] == "OKE" and d["ocid"] == cluster for d in deps):
                raise ValueError("OKE workload must reference a registered OKE dependency")
            absolute(oke["kubeconfig"], "kubeconfig")
            for field in ("namespace", "deployment"):
                identifier(oke[field], field)
            server, tls = oke.get("server", ""), oke.get("tlsServerName", "")
            if server:
                parsed = urlsplit(text(server, "server"))
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
                    raise ValueError("Use an HTTPS Kubernetes API endpoint")
            if tls and not re.fullmatch(r"[a-zA-Z0-9.-]+", text(tls, "tlsServerName")):
                raise ValueError("Invalid TLS server name")
            inspect = oke.get("inspectNodes", False)
            if type(inspect) is not bool:
                raise ValueError("inspectNodes must be boolean")
            workloads.append(dict(scope, appId=app_id, **oke))
    return {name: json.dumps(value, ensure_ascii=False, indent=2) + "\n" for name, value in (
        ("agent-connections.json", registrations), ("agent-credentials.json", credentials), ("oke-workloads.json", workloads))}


def write_bundle(config, output):
    files = render(config)  # Validate the entire bundle before creating anything.
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, content in files.items():
        with os.fdopen(os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        write_bundle(json.loads(Path(args.config).read_text()), args.output)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, "Configuration not generated: " + type(error).__name__ + ". Check schema and use a new output directory.\n")
    print("Generated 3 configuration files. No credentials read or OCI changes performed.")


if __name__ == "__main__":
    main()
