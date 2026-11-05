#!/usr/bin/env python3
"""Activate a preinstalled, root-controlled release; preserve databases and secrets."""

import argparse
import fcntl
import json
import os
import re
import stat
import subprocess
import time
import urllib.request
from pathlib import Path

CONFIG = Path("/etc/launchpad-deployment.json")


def trusted(path):
    """Reject symlinks and paths writable by a non-root principal."""
    for item in [path, *path.parents]:
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("Untrusted deployment path: " + str(item))


def validate(config, alias):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", config["service"]):
        raise ValueError("Invalid service")
    root = Path(config["release_root"])
    if (
        not root.is_absolute()
        or ".." in root.parts
        or not re.fullmatch(r"/[A-Za-z0-9_/-]+", str(root))
    ):
        raise ValueError("Invalid release root")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", alias) or alias in {".", ".."}:
        raise ValueError("Invalid release alias")
    release = config["releases"][alias]
    directory = release["directory"]
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", directory):
        raise ValueError("Invalid release directory")
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", release["version"]):
        raise ValueError("Invalid version")
    if type(config["port"]) is not int or not 1024 <= config["port"] <= 65535:
        raise ValueError("Invalid port")
    timeout = config.get("health_timeout_seconds", 45)
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise ValueError("Invalid health timeout")
    return root / directory, release["version"]


def health(port):
    # Ignore proxy environment for the local service health request.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
        return json.load(response)


def wait_health(port, version, timeout):
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = health(port)
            if result.get("status") == "UP" and result.get("version") == version:
                return True
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(1)


def restart(service):
    for command in [["systemctl", "daemon-reload"], ["systemctl", "restart", service]]:
        subprocess.run(command, check=True, timeout=60, capture_output=True)


def atomic_write(path, content):
    temp = path.with_suffix(".tmp")
    with os.fdopen(
        os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600),
        "wb",
    ) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def activate(
    config, alias, dropin, restart_fn=restart, health_fn=health, wait_fn=wait_health
):
    release, version = validate(config, alias)
    previous = dropin.read_bytes() if dropin.exists() else None
    before = health_fn(config["port"])
    if before.get("status") != "UP" or not before.get("version"):
        raise RuntimeError("Current release must be healthy before activation")
    content = (
        "[Service]\nExecStart=\nExecStart="
        + str(release)
        + "/venv/bin/python -m uvicorn service_desk.app:create_app --factory"
        " --host 127.0.0.1 --port " + str(config["port"]) + "\n"
    ).encode()
    atomic_write(dropin, content)
    timeout = config.get("health_timeout_seconds", 45)
    try:
        restart_fn(config["service"])
        if not wait_fn(config["port"], version, timeout):
            raise RuntimeError("Expected release did not become healthy")
    except (Exception, KeyboardInterrupt) as failure:
        if previous is None:
            dropin.unlink()
        else:
            atomic_write(dropin, previous)
        try:
            restart_fn(config["service"])
            if not wait_fn(config["port"], before["version"], timeout):
                raise RuntimeError("Previous version health check failed")
        except Exception as recovery:
            raise RuntimeError(
                "Activation failed; recovery also failed: operator intervention required"
            ) from recovery
        raise RuntimeError("Activation failed; previous version restored") from failure
    return {
        "status": "SUCCEEDED",
        "release": alias,
        "version": version,
        "previous_version": before["version"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run via the configured root deployment command")
    trusted(CONFIG)
    config = json.loads(CONFIG.read_text())
    release, _ = validate(config, args.release)
    trusted(release)
    # Venv Python may be a root-controlled symlink to the system interpreter.
    trusted(release / "venv")
    trusted(release / "venv/bin")
    trusted((release / "venv/bin/python").resolve(strict=True))
    directory = Path("/etc/systemd/system") / (config["service"] + ".service.d")
    directory.mkdir(mode=0o755, exist_ok=True)
    trusted(directory)
    dropin = directory / "90-launchpad-release.conf"
    if dropin.exists() or dropin.is_symlink():
        trusted(dropin)
    with open("/run/lock/launchpad-deployment.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(activate(config, args.release, dropin)))


if __name__ == "__main__":
    main()
