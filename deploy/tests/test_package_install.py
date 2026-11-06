import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import install_release as installer
from package_release import package


def staged(tmp_path, files):
    source = tmp_path / "stage"
    destination = tmp_path / "verified"
    source.mkdir()
    destination.mkdir()
    for name, content in files.items():
        if "/" not in name:
            (source / name).write_bytes(content)
    manifest = json.dumps(
        {
            "files": {
                name: hashlib.sha256(value).hexdigest() for name, value in files.items()
            }
        }
    ).encode()
    (source / "manifest.json").write_bytes(manifest)
    return source, destination, hashlib.sha256(manifest).hexdigest()


def test_verified_files_are_copied(tmp_path):
    source, target, digest = staged(
        tmp_path, {"requirements.txt": b"app==1.0\n", "app-1.0.whl": b"wheel"}
    )
    installer.copy_verified(source, target, digest)
    assert (target / "app-1.0.whl").read_bytes() == b"wheel"


def test_modified_wheel_rejected(tmp_path):
    source, target, digest = staged(
        tmp_path, {"requirements.txt": b"app==1.0\n", "app-1.0.whl": b"wheel"}
    )
    (source / "app-1.0.whl").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        installer.copy_verified(source, target, digest)


def test_modified_manifest_rejected(tmp_path):
    source, target, _digest = staged(
        tmp_path, {"requirements.txt": b"app==1.0\n", "app-1.0.whl": b"wheel"}
    )
    with pytest.raises(ValueError, match="Manifest checksum"):
        installer.copy_verified(source, target, "0" * 64)


@pytest.mark.parametrize("name", ["../escape.whl", "/etc/app.whl", "install.sh"])
def test_manifest_cannot_escape_or_run_scripts(tmp_path, name):
    source, target, digest = staged(
        tmp_path, {"requirements.txt": b"app==1.0\n", name: b"bad"}
    )
    with pytest.raises(ValueError, match="Unsafe manifest"):
        installer.copy_verified(source, target, digest)


def test_symlink_wheel_rejected(tmp_path):
    source, target, digest = staged(
        tmp_path, {"requirements.txt": b"app==1.0\n", "app-1.0.whl": b"wheel"}
    )
    (source / "app-1.0.whl").unlink()
    (source / "app-1.0.whl").symlink_to(source / "requirements.txt")
    with pytest.raises(OSError):
        installer.copy_verified(source, target, digest)


def test_remote_requirement_rejected(tmp_path):
    source, target, digest = staged(
        tmp_path,
        {
            "requirements.txt": b"app @ https://example.invalid/app.whl\n",
            "app-1.0.whl": b"wheel",
        },
    )
    with pytest.raises(ValueError, match="pinned"):
        installer.copy_verified(source, target, digest)


def test_package_manifest_matches_archive(tmp_path):
    import zipfile

    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "app-1.0.whl").write_bytes(b"wheel")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("app==1.0\n")
    output = tmp_path / "release.zip"
    result = package(wheels, requirements, output)
    with zipfile.ZipFile(output) as archive:
        assert (
            hashlib.sha256(archive.read("manifest.json")).hexdigest()
            == result["manifest_sha256"]
        )
        assert set(archive.namelist()) == {
            "manifest.json",
            "requirements.txt",
            "app-1.0.whl",
        }
