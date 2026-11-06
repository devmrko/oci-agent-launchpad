import hashlib
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import bootstrap_runtime as boot
from publish_runtime_secret import validate_runtime


def config():
    return {
        "region": "ap-seoul-1",
        "compartment_id": "ocid1.compartment.oc1.test",
        "artifact_id": "ocid1.genericartifact.oc1.test",
        "artifact_sha256": "a" * 64,
        "runtime_secret_id": "ocid1.vaultsecret.oc1.test",
        "release_alias": "memory-0.4.1",
        "app_version": "0.4.1",
        "manifest_sha256": "b" * 64,
        "model_region": "us-ashburn-1",
        "chat_model": "google.gemini-2.5-flash-lite",
        "embedding_model": "cohere.embed-v4.0",
    }


def test_config_has_no_secret_values():
    cfg = config()
    assert boot.validate_config(cfg)["releases"]["memory-0.4.1"]["version"] == "0.4.1"
    cfg["password"] = "not-allowed"
    with pytest.raises(ValueError):
        boot.validate_config(cfg)


@pytest.mark.parametrize("user", ["ADMIN", "SYS", "SYSTEM", "OWNER"])
def test_privileged_credentials_rejected(user):
    with pytest.raises(ValueError):
        validate_runtime(
            {
                "dsn": "example",
                "user": user,
                "password": "synthetic",
                "schema_owner": "OWNER",
                "store_id": "MEM",
                "compartment": "test",
            }
        )


@pytest.mark.parametrize("name", ["../escape.whl", "/etc/evil.whl", "install.sh"])
def test_archive_paths_rejected(tmp_path, name):
    archive = tmp_path / "package.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("manifest.json", "{}")
        z.writestr("requirements.txt", "")
        z.writestr(name, "bad")
    with pytest.raises(ValueError, match="Unsafe ZIP"):
        boot.unpack_verified(
            archive,
            tmp_path / "target",
            hashlib.sha256(archive.read_bytes()).hexdigest(),
        )
    assert not (tmp_path / "target").exists()


def test_tampered_package_rejected_before_extract(tmp_path):
    archive = tmp_path / "package.zip"
    archive.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        boot.unpack_verified(archive, tmp_path / "target", "0" * 64)


def test_reboot_does_not_fetch_or_overwrite_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(boot, "WORK", tmp_path)
    monkeypatch.setattr(boot, "trusted", Mock())
    fetch = Mock(side_effect=AssertionError("must not fetch on reboot"))
    monkeypatch.setattr(boot, "fetch_runtime", fetch)
    (tmp_path / "ready.json").write_text(json.dumps({"version": "0.4.1"}))
    boot.bootstrap(config())
    fetch.assert_not_called()


def test_download_reads_oci_response_raw_stream(tmp_path):
    import io

    payload = b"synthetic artifact"
    response = Mock()
    response.data.raw = io.BytesIO(payload)
    response.data.read = Mock(
        side_effect=AssertionError("OCI returns a requests response")
    )
    client = Mock()
    client.get_generic_artifact_content.return_value = response
    target = tmp_path / "release.zip"
    boot.download(
        client,
        "ocid1.genericartifact.oc1.test",
        target,
        hashlib.sha256(payload).hexdigest(),
    )
    assert target.read_bytes() == payload
    response.data.close.assert_called_once()


def test_code_install_is_readable_and_private_mask_restored(tmp_path, monkeypatch):
    import os
    import stat

    def prepare():
        (tmp_path / "code").mkdir(mode=0o755)

    def install(cfg, alias):
        (tmp_path / "code" / "module.py").write_text("pass")

    monkeypatch.setattr(boot, "prepare_commands", prepare)
    monkeypatch.setattr(boot, "install", install)
    old = os.umask(0o077)
    try:
        boot.install_readable({}, tmp_path / "config.json", "memory-0.4.1")
        (tmp_path / "private").write_text("synthetic")
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "code").stat().st_mode) == 0o755
    assert stat.S_IMODE((tmp_path / "code" / "module.py").stat().st_mode) == 0o644
    assert stat.S_IMODE((tmp_path / "private").stat().st_mode) == 0o600
