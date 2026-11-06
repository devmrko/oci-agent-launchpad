"""First-boot installer using instance identity and a runtime-only Vault secret."""

import base64
import hashlib
import json
import os
import pwd
import re
import secrets
import subprocess
import zipfile
from pathlib import Path

from activate_release import atomic_write, trusted, validate, wait_health
from bootstrap_release import main as prepare_commands
from install_release import install
from publish_runtime_secret import validate_runtime

CONFIG = Path("/etc/launchpad-bootstrap.json")
WORK = Path("/var/lib/launchpad-bootstrap")


def validate_config(cfg):
    required = {
        "region",
        "compartment_id",
        "artifact_id",
        "artifact_sha256",
        "runtime_secret_id",
        "release_alias",
        "app_version",
        "manifest_sha256",
        "model_region",
        "chat_model",
        "embedding_model",
    }
    if set(cfg) != required:
        raise ValueError("Unexpected or missing bootstrap setting")
    for key, value in cfg.items():
        if (
            not isinstance(value, str)
            or not value
            or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value)
        ):
            raise ValueError("Unsafe bootstrap setting: " + key)
    for key in ["artifact_sha256", "manifest_sha256"]:
        if not re.fullmatch(r"[a-f0-9]{64}", cfg[key]):
            raise ValueError("Invalid checksum")
    for key, prefix in [
        ("compartment_id", "ocid1.compartment."),
        ("artifact_id", "ocid1.genericartifact."),
        ("runtime_secret_id", "ocid1.vaultsecret."),
    ]:
        if not cfg[key].startswith(prefix):
            raise ValueError("Wrong OCID type")
    deployment = {
        "service": "launchpad-demo",
        "release_root": "/opt/launchpad/releases",
        "port": 8092,
        "staging_root": "/var/ocarun_staging/launchpad",
        "health_timeout_seconds": 60,
        "releases": {
            cfg["release_alias"]: {
                "directory": cfg["release_alias"],
                "version": cfg["app_version"],
                "manifest_sha256": cfg["manifest_sha256"],
            }
        },
    }
    validate(deployment, cfg["release_alias"])
    return deployment


def unpack_verified(archive, target, digest):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError("Artifact checksum mismatch")
    with zipfile.ZipFile(archive) as source:
        files = source.infolist()
        if len(files) > 301 or sum(x.file_size for x in files) > 1024 * 1024 * 1024:
            raise ValueError("Package exceeds bootstrap limits")
        names = set()
        for item in files:
            if item.filename not in {
                "manifest.json",
                "requirements.txt",
            } and not re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", item.filename):
                raise ValueError("Unsafe ZIP member")
            if item.filename in names or item.file_size > 200 * 1024 * 1024:
                raise ValueError("Duplicate or oversized ZIP member")
            names.add(item.filename)
        if not {"manifest.json", "requirements.txt"} <= names:
            raise ValueError("Missing package manifest")
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        for item in files:
            atomic_write(target / item.filename, source.read(item))


def fetch_runtime(client, identifier):
    bundle = client.get_secret_bundle(
        identifier, stage="CURRENT"
    ).data.secret_bundle_content
    if len(bundle.content) > 128 * 1024:
        raise ValueError("Runtime secret too large")
    return validate_runtime(json.loads(base64.b64decode(bundle.content)))


def unit_text(release, port=8092):
    return f"""[Unit]
Description=OCI Agent Launchpad
After=network-online.target
Wants=network-online.target
[Service]
User=launchpad
Group=launchpad
WorkingDirectory=/var/lib/launchpad
EnvironmentFile=/etc/launchpad-demo.env
ExecStart={release}/venv/bin/python -m uvicorn service_desk.app:create_app --factory --host 127.0.0.1 --port {port}
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/launchpad
[Install]
WantedBy=multi-user.target
"""


def download(client, identifier, archive, digest):
    if archive.exists() and hashlib.sha256(archive.read_bytes()).hexdigest() == digest:
        return
    response = client.get_generic_artifact_content(identifier)
    temporary = archive.with_suffix(".download")
    total = 0
    try:
        with temporary.open("wb") as stream:
            while True:
                chunk = response.data.raw.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 1024 * 1024 * 1024:
                    raise ValueError("Artifact exceeds limit")
                stream.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
            raise ValueError("Artifact checksum mismatch")
        os.replace(temporary, archive)
    finally:
        response.data.close()
        if temporary.exists():
            temporary.unlink()


def install_readable(deployment, commands, alias):
    """Only executable code installation uses a world-readable creation mask."""
    import sys

    previous_args = sys.argv
    previous_mask = os.umask(0o022)
    sys.argv = ["bootstrap_release.py", "--config", str(commands)]
    try:
        prepare_commands()
        install({**deployment, "staging_root": str(WORK / "staged")}, alias)
    finally:
        sys.argv = previous_args
        os.umask(previous_mask)


def bootstrap(cfg):
    import oci

    deployment = validate_config(cfg)
    release, _ = validate(deployment, cfg["release_alias"])
    WORK.mkdir(mode=0o700, parents=True, exist_ok=True)
    trusted(WORK)
    if (WORK / "ready.json").exists():
        print("BOOTSTRAP_ALREADY_INITIALIZED")
        return
    intent = WORK / "intent.json"
    unit = Path("/etc/systemd/system/launchpad-demo.service")
    if intent.exists():
        if json.loads(intent.read_text()) != cfg:
            raise ValueError("Existing bootstrap belongs to another configuration")
    elif unit.exists():
        raise ValueError("Refusing to overwrite an existing unmanaged service")
    else:
        atomic_write(intent, json.dumps(cfg, sort_keys=True).encode())
    print("BOOTSTRAP_PHASE identity", flush=True)
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    sdk = {"region": cfg["region"]}
    reader = oci.secrets.SecretsClient(sdk, signer=signer)
    print("BOOTSTRAP_PHASE runtime-secret", flush=True)
    runtime = fetch_runtime(reader, cfg["runtime_secret_id"])
    if runtime["compartment"] != cfg["compartment_id"]:
        raise ValueError("Runtime compartment mismatch")
    if (
        runtime.get("embedding_region") != cfg["model_region"]
        or runtime.get("embedding_model") != cfg["embedding_model"]
    ):
        raise ValueError(
            "Runtime embedding settings must match the granted model policy"
        )
    print("BOOTSTRAP_PHASE artifact", flush=True)
    artifact = oci.generic_artifacts_content.GenericArtifactsContentClient(
        sdk, signer=signer
    )
    archive = WORK / "release.zip"
    download(artifact, cfg["artifact_id"], archive, cfg["artifact_sha256"])
    unpack_verified(
        archive, WORK / "staged" / cfg["release_alias"], cfg["artifact_sha256"]
    )
    try:
        account = pwd.getpwnam("launchpad")
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--home",
                "/var/lib/launchpad",
                "--shell",
                "/usr/sbin/nologin",
                "launchpad",
            ],
            check=True,
            capture_output=True,
        )
        account = pwd.getpwnam("launchpad")
    data = Path("/var/lib/launchpad")
    data.mkdir(mode=0o700, exist_ok=True)
    os.chown(data, account.pw_uid, account.pw_gid)
    # Runtime secret is only ever written to the app-owned private directory.
    memory = data / "memory.json"
    atomic_write(memory, json.dumps(runtime).encode())
    os.chown(memory, account.pw_uid, account.pw_gid)
    commands = WORK / "deployment.json"
    atomic_write(commands, json.dumps(deployment).encode())
    print("BOOTSTRAP_PHASE install", flush=True)
    install_readable(deployment, commands, cfg["release_alias"])
    token_dir = data / ".run"
    token_dir.mkdir(mode=0o700, exist_ok=True)
    os.chown(token_dir, account.pw_uid, account.pw_gid)
    token_file = token_dir / "demo-accounts.json"
    if token_file.exists():
        accounts = json.loads(token_file.read_text())
    else:
        accounts = {
            secrets.token_urlsafe(32): {"subject": "demo-user", "can_write": True}
        }
        atomic_write(token_file, json.dumps(accounts).encode())
        os.chown(token_file, account.pw_uid, account.pw_gid)
    env = {
        "DESK_AUTH_MODE": "demo",
        "DESK_DATABASE_URL": "sqlite:////var/lib/launchpad/desk.db",
        "DESK_MODEL_BACKEND": "oci",
        "DESK_OCI_AUTH": "instance",
        "DESK_OCI_REGION": cfg["model_region"],
        "DESK_OCI_COMPARTMENT": cfg["compartment_id"],
        "DESK_MODEL_NAME": cfg["chat_model"],
        "DESK_MEMORY_CONFIG": str(memory),
    }
    text = (
        "\n".join(k + "=" + v for k, v in env.items())
        + "\nDESK_DEMO_ACCOUNTS='"
        + json.dumps(accounts)
        + "'\n"
    )
    atomic_write(Path("/etc/launchpad-demo.env"), text.encode())
    if unit.exists():
        trusted(unit)
    atomic_write(unit, unit_text(release).encode())
    subprocess.run(["systemctl", "daemon-reload"], check=True, capture_output=True)
    subprocess.run(
        ["systemctl", "enable", "launchpad-demo"], check=True, capture_output=True
    )
    print("BOOTSTRAP_PHASE start-service", flush=True)
    subprocess.run(
        ["systemctl", "restart", "launchpad-demo"],
        check=True,
        capture_output=True,
        timeout=90,
    )
    if not wait_health(8092, cfg["app_version"], 60):
        subprocess.run(
            ["systemctl", "stop", "launchpad-demo"], check=False, capture_output=True
        )
        raise RuntimeError("First application start failed")
    atomic_write(
        WORK / "ready.json",
        json.dumps(
            {"version": cfg["app_version"], "manifest_sha256": cfg["manifest_sha256"]}
        ).encode(),
    )
    print("BOOTSTRAP_READY version=" + cfg["app_version"])


def main():
    if os.geteuid() != 0:
        raise ValueError("Root bootstrap required")
    trusted(CONFIG)
    try:
        bootstrap(json.loads(CONFIG.read_text()))
    except Exception as error:  # noqa: BLE001 - prevent credentials in uncaught SDK tracebacks
        # SDK and DB exceptions can include request details: log only a safe class.
        print("BOOTSTRAP_FAILED type=" + type(error).__name__, flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
