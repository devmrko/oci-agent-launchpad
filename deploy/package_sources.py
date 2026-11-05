"""Create a source-only deployment archive from pinned Git commits."""

import argparse
import io
import subprocess
import tarfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--foundation", required=True)
parser.add_argument("--output", default=".run/oci-launchpad/sources.tar.gz")
args = parser.parse_args()
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(output, "w:gz") as bundle:
    for repo, revision, paths, prefix in [
        (
            args.foundation,
            "c98f69dd20c005ac5aa244dd03f110ddeed368dd",
            ["src", "pyproject.toml", "README.md"],
            "foundation/",
        ),
        (".", "2669f0d", ["examples/service-desk"], "launchpad/"),
    ]:
        raw = subprocess.check_output(["git", "-C", repo, "archive", revision, *paths])
        with tarfile.open(fileobj=io.BytesIO(raw)) as source:
            for member in source.getmembers():
                stream = source.extractfile(member) if member.isfile() else None
                member.name = prefix + member.name
                bundle.addfile(member, stream)
print(str(output))
