"""Explicit requirement bindings and file-level change reports; never executes tests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from check_spec_links import check
from requirement_handoff import digest, fingerprint, load_bundle, read, status, text, write_new


def local(root, name):
    name = Path(name)
    if name.is_absolute():
        raise ValueError("Use repository-relative paths")
    path = (Path(root).resolve() / name).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("Path leaves repository")
    return path


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def source_state(root, bundle, requirement, latest):
    path = local(root, bundle)
    source, records = load_bundle(path)
    report = status(path, latest)
    row = next((r for r in records if r["id"] == requirement), None)
    state = next((r["status"] for r in report["requirements"] if r["id"] == requirement), "MISSING")
    return {"fingerprint": fingerprint(source, row) if row else None,
            "state": state, "project_id": source["id"]}


def target_state(root, bundle, requirement):
    directory = local(root, bundle)
    spec = local(root, str(Path(bundle) / "spec.md")).read_text()
    manifest_path = local(root, str(Path(bundle) / "traceability.json"))
    manifest = read(manifest_path)
    entries = manifest["requirements"]
    mapping = next((r for r in entries if r["id"] == requirement), None)
    sections = list(re.finditer(r"^## .*?$", spec, re.M))
    section = None
    for index, match in enumerate(sections):
        if re.match(r"^## " + re.escape(requirement) + r"\b", match.group()):
            section = spec[match.start():sections[index+1].start() if index+1 < len(sections) else len(spec)]
            break
    paths = set()
    if mapping:
        paths.update(mapping["implementation"])
        paths.update(t["path"] for t in mapping["tests"])
    paths.update(str(Path(bundle) / n) for n in ("design.md", "tasks.md"))
    artifacts = {p: file_hash(local(root, p)) for p in sorted(paths)}
    return {"section_hash": digest(section) if section else None, "mapping": mapping,
            "artifacts": artifacts}, entries


def bind(root, handoff, source_id, target, target_id, latest, reason):
    text(reason)
    source = source_state(root, handoff, source_id, latest)
    if source["state"] != "REVIEW_RECORDED":
        raise ValueError("Only reviewed, current requirements can be linked")
    check(root, target)
    state, _ = target_state(root, target, target_id)
    if not state["mapping"] or not state["section_hash"]:
        raise ValueError("Target requirement is missing")
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "handoff": handoff, "source_requirement": source_id, "source": source,
            "target_bundle": target, "target_requirement": target_id, "target": state,
            "reason": reason, "identity_verified": False}


def inspect(root, baseline, latest):
    if baseline["schema_version"] != 1:
        raise ValueError("Unsupported baseline")
    source = source_state(root, baseline["handoff"], baseline["source_requirement"], latest)
    if source["project_id"] != baseline["source"]["project_id"]:
        raise ValueError("Source project changed")
    current, entries = target_state(root, baseline["target_bundle"], baseline["target_requirement"])
    reasons = []
    if source["state"] != "REVIEW_RECORDED":
        reasons.append("source_review_not_current")
    if source["fingerprint"] != baseline["source"]["fingerprint"]:
        reasons.append("source_requirement_changed")
    if current["section_hash"] != baseline["target"]["section_hash"]:
        reasons.append("target_requirement_changed")
    if current["mapping"] != baseline["target"]["mapping"]:
        reasons.append("target_mapping_changed")
    try:
        check(root, baseline["target_bundle"])
    except (ValueError, OSError, KeyError, TypeError, SyntaxError):
        reasons.append("target_links_invalid")
    before, after = baseline["target"]["artifacts"], current["artifacts"]
    changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    if changed:
        reasons.append("artifact_changed_or_missing")
    affected = {baseline["target_requirement"]} if reasons else set()
    for entry in entries:
        paths = set(entry["implementation"]) | {t["path"] for t in entry["tests"]}
        if paths.intersection(changed):
            affected.add(entry["id"])
    tests = {(t["path"], t["case"]) for r in entries if r["id"] in affected for t in r["tests"]}
    if reasons:
        tests.update((t["path"], t["case"]) for t in baseline["target"]["mapping"]["tests"])
    return {"status": "REVIEW_REQUIRED" if reasons else "UNCHANGED", "reasons": reasons,
            "source_requirement": baseline["source_requirement"],
            "target_requirement": baseline["target_requirement"],
            "changed_files": changed, "potentially_affected_requirements": sorted(affected),
            "tests_to_review": [{"path": p, "case": c} for p, c in sorted(tests)],
            "tests_executed": False, "scope": "provided_source_and_repository_files"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("bind")
    p.add_argument("--handoff", required=True)
    p.add_argument("--source-requirement", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--target-requirement", required=True)
    p.add_argument("--source", required=True, help="Explicit current interview snapshot")
    p.add_argument("--reason", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("check")
    p.add_argument("baseline")
    p.add_argument("--source", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.command == "bind":
            result = bind(root, args.handoff, args.source_requirement, args.target,
                          args.target_requirement, args.source, args.reason)
            write_new(args.output, result)
            print(json.dumps({"status": "BOUND", "identity_verified": False}))
        else:
            result = inspect(root, read(args.baseline), args.source)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(2 if result["status"] == "REVIEW_REQUIRED" else 0)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError):
        parser.exit(1, "Invalid source, binding, mapping or path; no unchanged result was produced.\n")
