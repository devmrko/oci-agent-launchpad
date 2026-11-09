"""Validate requirement-to-source/test links; does not run tests or certify semantics."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re


def check(root, bundle):
    root = Path(root).resolve()
    def local(name):
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Missing or external file: {name}")
        return path
    bundle = Path(bundle)
    spec = local(str(bundle / "spec.md"))
    manifest_path = local(str(bundle / "traceability.json"))
    manifest = json.loads(manifest_path.read_text())
    headings = re.findall(r"^## (REQ-\d+)\b", spec.read_text(), re.M)
    if not headings or len(headings) != len(set(headings)):
        raise ValueError("Requirement headings must exist and have unique IDs")
    records = manifest["requirements"]
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)) or set(ids) != set(headings):
        raise ValueError("Requirement IDs and traceability records differ")
    files = {spec, manifest_path, local(str(bundle / "design.md")), local(str(bundle / "tasks.md"))}
    for record in records:
        if not record["implementation"] or not record["tests"]:
            raise ValueError(f"Empty mapping: {record['id']}")
        for source in record["implementation"]:
            files.add(local(source))
        for test in record["tests"]:
            path = local(test["path"])
            files.add(path)
            tree = ast.parse(path.read_text())
            cases = {f"{c.name}.{m.name}" for c in tree.body if isinstance(c, ast.ClassDef)
                     for m in c.body if isinstance(m, ast.FunctionDef) and m.name.startswith("test_")}
            if test["case"] not in cases:
                raise ValueError(f"Missing test: {test['case']}")
    return {"status": "links_valid", "requirements": ids, "tests_executed": False,
            "files": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Repository-relative specification directory")
    args = parser.parse_args()
    try:
        result = check(Path(__file__).resolve().parents[1], args.bundle)
    except (ValueError, KeyError, TypeError, SyntaxError) as error:
        parser.exit(1, f"Specification link check failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
