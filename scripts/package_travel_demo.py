"""Package the verified travel demo for local use; no deployment or model calls."""
import argparse
import hashlib
import json
import stat
from pathlib import Path, PurePosixPath
import zipfile

from check_spec_links import check
from requirement_handoff import read
from spec_evidence import inspect

BUNDLE = "specs/travel-allowance"
APP = "examples/enterprise-ai-web"
FILES = tuple(f"{APP}/{name}" for name in (
    "allowance.py", "cli.py", "server.py", "index.html", "test_cli.py", "test_server.py")) + tuple(
    f"{BUNDLE}/{name}" for name in ("spec.md", "design.md", "tasks.md", "traceability.json"))
RUN = """# 출장비 예제 실행

Python 3.12 이상에서 압축을 푼 폴더로 이동하세요. 추가 패키지·OCI 계정 없이 실행합니다.

터미널 계산: `python3 examples/enterprise-ai-web/cli.py 14`

웹 실행: `python3 examples/enterprise-ai-web/server.py --offline`

브라우저에서 http://127.0.0.1:8768 을 열면 규정 계산을 사용할 수 있습니다. 포트가 사용 중이면 `--port 8769`로 바꾸세요. 종료는 Ctrl+C입니다.

검증: `python3 -S -m unittest discover -s examples/enterprise-ai-web -p 'test_*.py'`

가상 규정의 14박 한도는 1,400,000원이며 15박은 거부합니다. 실제 지급·신청·승인을 수행하지 않습니다.

test-evidence.json은 패키지 생성 시 현재 파일과 일치한 테스트 기록입니다. PACKAGE.json은 각 포함 파일의 SHA-256을 기록합니다. 실행 후 수정한 파일까지 검증한 것은 아닙니다. 실행 환경의 차이와 화면 시각 품질·실제 OCI 연결·운영 배포는 별도 확인 대상입니다. 명세의 추가 문서 링크는 전체 저장소에서 확인하세요.

소스: https://github.com/devmrko/oci-agent-launchpad
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(root, evidence, output):
    root, output = Path(root).resolve(), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Output exists")
    if evidence.get("bundle") != BUNDLE or evidence.get("tests_executed") is not True:
        raise ValueError("Expected executed travel demo evidence")
    if not inspect(root, evidence)["usable_pass"]:
        raise ValueError("Current passing evidence required")
    current = check(root, BUNDLE)
    if set(current["files"]) != set(FILES):
        raise ValueError("Package allowlist differs from linked files")
    payload = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Invalid source path")
        payload[name] = path.read_bytes()
        if sha(payload[name]) != evidence["files"].get(name):
            raise ValueError("Source changed while packaging")
    payload["RUN.md"] = RUN.encode()
    payload["test-evidence.json"] = (json.dumps(evidence, ensure_ascii=False, indent=2)+"\n").encode()
    manifest = {"schema_version": 1, "purpose": "travel-demo-local-only", "files": {name: sha(data) for name, data in payload.items()},
                "evidence_status": "PASS", "deployment_performed": False}
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
        archive.writestr("PACKAGE.json", json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    return {"status": "PACKAGED", "files": len(payload), "archive_sha256": sha(output.read_bytes()), "deployment_performed": False}


def verify(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if any(entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) for entry in infos):
            raise ValueError("Only regular archive files are supported")
        names = [entry.filename for entry in infos]
        if len(names) > 100 or len(set(names)) != len(names) or sum(e.file_size for e in infos) > 16 * 1024 * 1024:
            raise ValueError("Invalid archive size or duplicate files")
        for name in names:
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name:
                raise ValueError("Invalid archive path")
        manifest = json.loads(archive.read("PACKAGE.json"))
        if manifest.get("schema_version") != 1 or manifest.get("purpose") != "travel-demo-local-only":
            raise ValueError("Unsupported manifest")
        expected = set(FILES) | {"RUN.md", "test-evidence.json"}
        if set(manifest["files"]) != expected or set(names) != expected | {"PACKAGE.json"}:
            raise ValueError("Unexpected archive files")
        for name, digest in manifest["files"].items():
            if sha(archive.read(name)) != digest:
                raise ValueError("File hash mismatch")
    return {"status": "HASHES_MATCH", "tests_executed": False, "deployment_performed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("build")
    pack.add_argument("--evidence", required=True, type=Path)
    pack.add_argument("--output", required=True, type=Path)
    check_zip = commands.add_parser("verify")
    check_zip.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        result = build(Path(__file__).resolve().parents[1], read(args.evidence), args.output) if args.command == "build" else verify(args.archive)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        parser.exit(1, "Package check failed. Check current evidence, allowlisted files and a new output path.\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
