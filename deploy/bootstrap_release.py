#!/usr/bin/env python3
"""Administrator setup for the verified installer; never installs an app release."""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from activate_release import trusted, validate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
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
    staging.mkdir(mode=0o755, parents=True, exist_ok=True)
    if staging.is_symlink():
        raise ValueError("Staging root cannot be a symlink")
    shutil.chown(staging, user="ocarun", group="oracle-cloud-agent")
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
