"""Export allowlisted sources from two explicit Git revisions, without credentials."""

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def export(repo, revision, paths, prefix):
    # --end-of-options prevents a revision being interpreted as a Git option.
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
    raw = git(repo, "archive", "--format=tar", commit, *paths)
    entries = []
    with tarfile.open(fileobj=io.BytesIO(raw)) as source:
        for member in source.getmembers():
            if not member.isfile() and not member.isdir():
                raise ValueError("Source links and special entries are not supported")
            if member.isfile():
                if any(part.startswith(".env") or part in {".oci", ".git", ".run", ".tools"}
                       for part in Path(member.name).parts):
                    raise ValueError("Private configuration path in source export")
                entries.append((prefix + member.name, source.extractfile(member).read(), member.mode))
    return commit, entries


def package_sources(foundation, foundation_revision, launchpad, launchpad_revision, output):
    if output.exists():
        raise ValueError("Output already exists; choose a new build path")
    fsha, fentries = export(foundation, foundation_revision,
                           ["src", "pyproject.toml", "README.md"], "foundation/")
    lsha, lentries = export(launchpad, launchpad_revision,
                           ["examples/service-desk", "deploy/package_release.py"], "launchpad/")
    source = {"schema_version": 1, "foundation_commit": fsha, "launchpad_commit": lsha}
    entries = fentries + lentries + [("source.json", json.dumps(source, sort_keys=True).encode(), 0o644)]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as bundle:
                for name, content, mode in sorted(entries):
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    info.mode = mode
                    info.mtime = 0
                    bundle.addfile(info, io.BytesIO(content))
    return {**source, "source_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--foundation", type=Path, required=True)
    p.add_argument("--foundation-revision", required=True)
    p.add_argument("--launchpad", type=Path, default=Path("."))
    p.add_argument("--launchpad-revision", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(package_sources(a.foundation, a.foundation_revision, a.launchpad,
                                     a.launchpad_revision, a.output)))


if __name__ == "__main__":
    main()
