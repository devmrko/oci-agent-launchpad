#!/usr/bin/env python3
"""Verify and install a staged offline release, then activate with rollback."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

from activate_release import CONFIG, activate, trusted, validate


def read_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("Invalid package file")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Package file too large")
        return data


def copy_verified(stage, destination, expected):
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("Invalid manifest checksum")
    raw = read_regular(stage / "manifest.json", 128 * 1024)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Manifest checksum mismatch")
    files = json.loads(raw)["files"]
    if (
        not isinstance(files, dict)
        or not 2 <= len(files) <= 300
        or "requirements.txt" not in files
    ):
        raise ValueError("Invalid manifest file list")
    total = 0
    for name, digest in files.items():
        if name != "requirements.txt" and not re.fullmatch(
            r"[A-Za-z0-9_.+-]+\.whl", name
        ):
            raise ValueError("Unsafe manifest path")
        data = read_regular(stage / name, 200 * 1024 * 1024)
        total += len(data)
        if total > 1024 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Package checksum or size mismatch")
        with (destination / name).open("xb") as stream:
            stream.write(data)
    for line in (destination / "requirements.txt").read_text().splitlines():
        if line and not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", line):
            raise ValueError("Only pinned requirements are accepted")


def install(config, alias):
    release, version = validate(config, alias)
    expected = config["releases"][alias]["manifest_sha256"]
    stage_root = Path(config["staging_root"])
    if (
        not stage_root.is_absolute()
        or ".." in stage_root.parts
        or not re.fullmatch(r"/[A-Za-z0-9_/-]+", str(stage_root))
    ):
        raise ValueError("Invalid staging root")
    trusted(release.parent)
    if release.exists():
        trusted(release)
        marker = release / ".manifest-sha256"
        trusted(marker)
        if marker.read_text() != expected:
            raise ValueError("Existing release belongs to different package")
        return
    release.mkdir(mode=0o755)
    try:
        bundle = release / "packages"
        bundle.mkdir(mode=0o700)
        copy_verified(stage_root / alias, bundle, expected)

        def run(args):
            subprocess.run(args, check=True, timeout=600, capture_output=True)

        run(["/usr/bin/python3.12", "-m", "venv", str(release / "venv")])
        python = str(release / "venv/bin/python")
        run(
            [
                python,
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-index",
                "--only-binary=:all:",
                "--find-links",
                str(bundle),
                "-r",
                str(bundle / "requirements.txt"),
            ]
        )
        run([python, "-m", "pip", "check"])
        run(
            [
                python,
                "-c",
                'import service_desk.app; import importlib.metadata as m; assert m.version("launchpad-service-desk") == '
                + repr(version),
            ]
        )
        (release / ".manifest-sha256").write_text(expected)
    except BaseException:
        # Only the newly created, root-controlled directory is removed.
        shutil.rmtree(release)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("release")
    a = p.parse_args()
    if os.geteuid() != 0:
        p.error("Root deployment command required")
    trusted(CONFIG)
    config = json.loads(CONFIG.read_text())
    validate(config, a.release)
    with open("/run/lock/launchpad-deployment.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        install(config, a.release)
        directory = Path("/etc/systemd/system") / (config["service"] + ".service.d")
        directory.mkdir(mode=0o755, exist_ok=True)
        trusted(directory)
        dropin = directory / "90-launchpad-release.conf"
        if dropin.exists() or dropin.is_symlink():
            trusted(dropin)
        print(json.dumps(activate(config, a.release, dropin)))


if __name__ == "__main__":
    main()
