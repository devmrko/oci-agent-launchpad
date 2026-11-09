"""Execute mapped unittest cases and check freshness of local JSON evidence."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from check_spec_links import check
from requirement_handoff import read, write_new


def execute(root, bundle, output, timeout=30):
    root = Path(root).resolve()
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Evidence output already exists")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be positive")
    before = check(root, bundle)
    manifest = read(root / bundle / "traceability.json")
    cases = sorted({(t["path"], t["case"]) for r in manifest["requirements"] for t in r["tests"]})
    results = []
    worker = Path(__file__).with_name("spec_test_worker.py").resolve()
    for path, case in cases:
        item = {"path": path, "case": case, "status": "ERROR"}
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "result.json"
            try:
                process = subprocess.run([sys.executable, str(worker), str(root / path), case, str(report)],
                                         cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         timeout=timeout, check=False)
                if process.returncode == 0 and report.is_file():
                    counts = json.loads(report.read_text())
                    item["counts"] = counts
                    item["status"] = "PASS" if counts["run"] == 1 and not any(
                        v for k, v in counts.items() if k != "run") else "NOT_PASSED"
            except subprocess.TimeoutExpired:
                item["status"] = "TIMEOUT"
        results.append(item)
    try:
        stable = before["files"] == check(root, bundle)["files"]
    except (ValueError, KeyError, TypeError, SyntaxError, OSError):
        stable = False
    lookup = {(r["path"], r["case"]): r["status"] for r in results}
    requirements = {r["id"]: ("PASS" if all(lookup[(t["path"], t["case"])] == "PASS"
                    for t in r["tests"]) else "NOT_PASSED") for r in manifest["requirements"]}
    result = {"schema_version": 1, "bundle": str(bundle), "recorded_at": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "files": before["files"], "stable_during_run": stable,
              "status": "INVALIDATED" if not stable else ("PASS" if all(v == "PASS" for v in requirements.values()) else "NOT_PASSED"),
              "requirements": requirements, "tests": results, "tests_executed": True}
    write_new(output, result)
    return result


def inspect(root, evidence):
    if evidence.get("schema_version") != 1 or evidence.get("status") not in {"PASS", "NOT_PASSED", "INVALIDATED"}:
        raise ValueError("Unsupported evidence")
    if not isinstance(evidence.get("files"), dict) or not evidence["files"]:
        raise ValueError("Missing evidence snapshot")
    try:
        current = check(root, evidence["bundle"])["files"]
        changed = sorted(p for p in set(current) | set(evidence["files"]) if current.get(p) != evidence["files"].get(p))
        freshness = "STALE" if changed else "CURRENT"
    except (ValueError, KeyError, TypeError, SyntaxError, OSError):
        changed, freshness = [], "INVALID"
    return {"freshness": freshness, "recorded_status": evidence["status"], "changed_files": changed,
            "usable_pass": freshness == "CURRENT" and evidence["status"] == "PASS" and evidence.get("stable_during_run") is True,
            "tests_executed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("bundle", type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--timeout", type=float, default=30)
    verify = sub.add_parser("check")
    verify.add_argument("evidence", type=Path)
    for command in (run, verify):
        command.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                             help="Project root; defaults to this repository")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        result = execute(root, args.bundle, args.output, args.timeout) if args.command == "run" else inspect(root, read(args.evidence))
    except (ValueError, KeyError, TypeError, SyntaxError, OSError):
        parser.exit(1, "Evidence operation failed; check inputs and output path.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" or result.get("usable_pass") else 2


if __name__ == "__main__":
    sys.exit(main())
