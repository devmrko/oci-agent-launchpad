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
