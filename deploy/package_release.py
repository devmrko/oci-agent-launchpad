"""Bundle an offline wheelhouse with a pinned manifest for OCI DevOps delivery."""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


def package(wheels, requirements, output):
    content = requirements.read_bytes()
    for line in content.decode().splitlines():
        if line and not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", line):
            raise ValueError("Requirements must contain pinned package versions only")
    files = {"requirements.txt": content}
    for path in sorted(wheels.glob("*.whl")):
        if path.is_symlink():
            raise ValueError("Symlink wheel refused")
        files[path.name] = path.read_bytes()
    if len(files) < 2:
        raise ValueError("Wheelhouse is empty")
    manifest = json.dumps(
        {"files": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}},
        sort_keys=True,
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in {**files, "manifest.json": manifest}.items():
            archive.writestr(name, data)
    return {
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "bundle_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "files": len(files),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wheels", type=Path, required=True)
    p.add_argument("--requirements", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(package(a.wheels, a.requirements, a.output)))


if __name__ == "__main__":
    main()
