#!/usr/bin/env python3
"""Administrator setup for the verified installer; never installs an app release."""

import argparse
import json
import os
import pwd
import stat
import re
import shutil
import subprocess
from pathlib import Path

from activate_release import trusted, validate


def probe_access(path, flag):
    result = subprocess.run(
        ["/usr/sbin/runuser", "-u", "ocarun", "--", "/usr/bin/test", flag, str(path)],
        capture_output=True, timeout=10,
    )
    return result.returncode == 0


def check_staging(staging, uid, probe=probe_access):
    # The root-owned ancestors prevent replacement of the agent-owned leaf.
    trusted(staging.parent)
    info = staging.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError("Staging root must be a real directory: " + str(staging))
    if info.st_uid != uid or info.st_mode & 0o022:
        raise ValueError("Staging root must belong to ocarun without group/other write: " + str(staging))
    for parent in reversed(staging.parents):
        if not probe(parent, "-x"):
            raise ValueError("ocarun cannot traverse staging ancestor: " + str(parent))
    for flag in ["-x", "-w"]:
        if not probe(staging, flag):
            raise ValueError("ocarun lacks staging access " + flag + ": " + str(staging))


def prepare_staging(staging, uid):
    if staging == Path("/"):
        raise ValueError("Filesystem root cannot be a staging directory")
    # Reject unsafe existing ancestors before mkdir/chown can follow them.
    for parent in reversed(staging.parents):
        if parent.exists() or parent.is_symlink():
            trusted(parent)
    if staging.exists() or staging.is_symlink():
        info = staging.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, uid} or info.st_mode & 0o022:
            raise ValueError("Unsafe existing staging directory: " + str(staging))
        if info.st_uid == 0 and any(staging.iterdir()):
            raise ValueError("Refusing to change ownership of nonempty root-owned staging: " + str(staging))
    staging.mkdir(mode=0o700, parents=True, exist_ok=True)
    trusted(staging.parent)
    shutil.chown(staging, user="ocarun", group="oracle-cloud-agent")
    check_staging(staging, uid)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--check", action="store_true", help="Read-only staging and release-root checks; no configuration changes")
    a = p.parse_args()
    if os.geteuid() != 0:
        p.error("Root required")
    config = json.loads(a.config.read_text())
    root = Path(config["release_root"])
    staging = Path(config["staging_root"])
    if (
        not staging.is_absolute()
        or ".." in staging.parts
        or not re.fullmatch(r"/[A-Za-z0-9_/-]+", str(staging))
    ):
        raise ValueError("Invalid staging root")
    commands = []
    for alias, release in config["releases"].items():
        validate(config, alias)
        commands.append("/usr/local/sbin/launchpad-activate " + alias)
        if "manifest_sha256" in release:
            if not re.fullmatch(r"[a-f0-9]{64}", release["manifest_sha256"]):
                raise ValueError("Invalid manifest checksum")
            commands.append("/usr/local/sbin/launchpad-deploy " + alias)
    if not commands:
        raise ValueError("At least one release required")
    uid = pwd.getpwnam("ocarun").pw_uid
    if a.check:
        trusted(root)
        check_staging(staging, uid)
        print("Release root trusted; ocarun staging traversal/write checks passed. No changes made.")
        return
    prepare_staging(staging, uid)
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    trusted(root)
    library = Path("/usr/local/lib/launchpad")
    library.mkdir(mode=0o755, parents=True, exist_ok=True)
    trusted(library)
    source = Path(__file__).parent
    for filename in ["activate_release.py", "install_release.py"]:
        target = library / filename
        if target.exists() or target.is_symlink():
            trusted(target)
        shutil.copyfile(source / filename, target)
        target.chmod(0o644)
    for command, script in [
        ("launchpad-activate", "activate_release.py"),
        ("launchpad-deploy", "install_release.py"),
    ]:
        target = Path("/usr/local/sbin") / command
        if target.exists() or target.is_symlink():
            trusted(target)
        target.write_text(
            "#!/bin/sh\nexec /usr/bin/python3 /usr/local/lib/launchpad/"
            + script
            + ' "$@"\n'
        )
        target.chmod(0o755)
    target = Path("/etc/launchpad-deployment.json")
    if target.exists() or target.is_symlink():
        trusted(target)
    target.write_text(json.dumps(config, indent=2))
    target.chmod(0o600)
    sudoers = Path("/etc/sudoers.d/launchpad-deploy")
    temporary = Path("/etc/sudoers.d/.launchpad-deploy.tmp")
    if temporary.exists() or temporary.is_symlink():
        trusted(temporary)
    temporary.write_text("ocarun ALL=(root) NOPASSWD: " + ", ".join(commands) + "\n")
    temporary.chmod(0o440)
    subprocess.run(["/usr/sbin/visudo", "-cf", str(temporary)], check=True)
    os.replace(temporary, sudoers)
    print("Installer and allowed releases configured; running app unchanged.")


if __name__ == "__main__":
    main()
