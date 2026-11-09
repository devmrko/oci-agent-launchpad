"""Portable interview drafts and self-declared human review records; no AI calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Input must be a regular JSON file of at most 4 MiB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 8000:
        raise ValueError("Expected nonempty bounded text")
    return value


def snapshot(value):
    if value["schemaVersion"] != 1 or not isinstance(value["id"], str):
        raise ValueError("Unsupported source schema")
    text(value["id"])
    if type(value["revision"]) is not int or value["revision"] < 1:
        raise ValueError("Invalid revision")
    questions, answers = value["questions"], value["answers"]
    if not isinstance(questions, list) or not isinstance(answers, list) or len(questions) > 100 or len(answers) > 500:
        raise ValueError("Invalid source size")
    qids, aids, latest = set(), set(), {}
    for question in questions:
        qid = text(question["id"])
        text(question["text"])
        if qid in qids:
            raise ValueError("Duplicate question ID")
        qids.add(qid)
    for answer in answers:
        aid, qid = text(answer["id"]), text(answer["questionId"])
        text(answer["text"])
        if aid in aids or qid not in qids or answer["status"] not in ("answered", "deferred"):
            raise ValueError("Invalid answer identity, question or status")
        prior = latest.get(qid)
        if answer.get("supersedes") != (prior["id"] if prior else None):
            raise ValueError("Answer revisions must form one ordered chain per question")
        aids.add(aid)
        latest[qid] = answer
    return latest


def write_new(path, value):
    with open(path, "x", encoding="utf-8", opener=lambda p, f: os.open(p, f, 0o600)) as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def draft(source, destination):
    source = read(source)
    latest = snapshot(source)
    requirements = []
    for answer in latest.values():
        if answer["status"] == "answered":
            requirements.append({"id": f"REQ-{len(requirements)+1:03}",
                                 "text": answer["text"], "answer_ids": [answer["id"]]})
    package = {"schema_version": 1, "project_id": source["id"], "source_revision": source["revision"],
               "requirements": requirements,
               "unresolved_question_ids": [q["id"] for q in source["questions"]
                                           if q["id"] not in latest or latest[q["id"]]["status"] == "deferred"]}
    destination = Path(destination)
    destination.mkdir(mode=0o700)  # Existing directories are never overwritten.
    write_new(destination / "source.json", source)
    write_new(destination / "requirements.json", package)
    (destination / "reviews").mkdir(mode=0o700)
    return {"status": "DRAFT", "requirements": len(requirements),
            "unresolved": len(package["unresolved_question_ids"])}


def load_bundle(bundle):
    bundle = Path(bundle)
    source, package = read(bundle / "source.json"), read(bundle / "requirements.json")
    latest = snapshot(source)
    if package["schema_version"] != 1 or package["project_id"] != source["id"]:
        raise ValueError("Source and requirements belong to different projects")
    if package["source_revision"] != source["revision"]:
        raise ValueError("Source revision changed; generate a new draft")
    records = package["requirements"]
    if not isinstance(records, list) or len(records) > 100:
        raise ValueError("Invalid requirements")
    allowed = {a["id"] for a in latest.values() if a["status"] == "answered"}
    seen = set()
    for record in records:
        rid = text(record["id"])
        text(record["text"])
        if rid in seen:
            raise ValueError("Duplicate requirement ID")
        seen.add(rid)
        refs = record["answer_ids"]
        if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)) or not set(refs) <= allowed:
            raise ValueError("Requirement must refer to current answered evidence")
    return source, records


def fingerprint(source, record):
    return digest({"source": source, "requirement": record})


def review(bundle, requirement, reviewer):
    source, records = load_bundle(bundle)
    text(reviewer)
    matches = [record for record in records if record["id"] == requirement]
    if not matches:
        raise ValueError("Unknown requirement")
    event = {"requirement_id": requirement, "reviewer": reviewer,
             "identity_verified": False, "at": datetime.now(timezone.utc).isoformat(),
             "fingerprint": fingerprint(source, matches[0]), "decision": "reviewed"}
    folder = Path(bundle) / "reviews"
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Invalid review directory")
    write_new(folder / f"{uuid.uuid4()}.json", event)
    return {"status": "REVIEW_RECORDED", "identity_verified": False}


def status(bundle, current=None):
    source, records = load_bundle(bundle)
    changed = False
    if current:
        fresh = read(current)
        snapshot(fresh)
        if fresh["id"] != source["id"] or fresh["revision"] < source["revision"]:
            raise ValueError("Expected same project and a current or newer revision")
        changed = digest(fresh) != digest(source)
    folder = Path(bundle) / "reviews"
    if folder.is_symlink():
        raise ValueError("Invalid review directory")
    events = [read(p) for p in sorted(folder.glob("*.json"))]
    result = []
    for record in records:
        reviews = [e for e in events if e["requirement_id"] == record["id"]]
        valid = any(e["decision"] == "reviewed" and e["fingerprint"] == fingerprint(source, record) for e in reviews)
        state = "REVIEW_REQUIRED" if changed or (reviews and not valid) else "REVIEW_RECORDED" if valid else "DRAFT"
        result.append({"id": record["id"], "status": state})
    return {"scope": "supplied_current_source" if current else "captured_snapshot_only",
            "identity_verified": False, "source_changed": changed, "requirements": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("draft")
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser("record-review")
    p.add_argument("bundle")
    p.add_argument("--requirement", required=True)
    p.add_argument("--reviewer", required=True)
    p = commands.add_parser("status")
    p.add_argument("bundle")
    p.add_argument("--source")
    args = parser.parse_args()
    try:
        if args.command == "draft":
            result = draft(args.source, args.output)
        elif args.command == "record-review":
            result = review(args.bundle, args.requirement, args.reviewer)
        else:
            result = status(args.bundle, args.source)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Input, reference, revision or output path is invalid. No source content is printed.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
