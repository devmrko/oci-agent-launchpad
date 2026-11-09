"""Reproduce the synthetic SDD walkthrough in a new isolated directory."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sys

from check_spec_links import check
from requirement_handoff import draft, read, review, status, write_new
from spec_evidence import execute, inspect as inspect_evidence
from spec_impact import bind, inspect as inspect_impact


BUNDLE = "specs/travel-allowance"
SOURCE = "specs/interview-handoff/interview.example.json"


def run_demo(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    files = check(root, BUNDLE)["files"]
    output.mkdir(mode=0o700)  # Refuse reuse before executing tests or writing records.
    workspace = output / "workspace"
    workspace.mkdir(mode=0o700)
    for name in [*files, SOURCE]:
        destination = workspace / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination)
    source = workspace / SOURCE
    handoff = workspace / "handoff"
    draft_result = draft(source, handoff)
    review(handoff, "REQ-001", "synthetic-demo-only-not-a-human-approval")
    baseline = bind(workspace, "handoff", "REQ-001", BUNDLE, "REQ-001", source,
                    "Synthetic demonstration: nights 1–10 times 100000 matches the existing calculation requirement.")
    write_new(workspace / "binding.json", baseline)
    evidence = execute(workspace, Path(BUNDLE), workspace / "test-evidence.json")
    initial = {"impact": inspect_impact(workspace, baseline, source),
               "evidence": inspect_evidence(workspace, evidence),
               "review": status(handoff, source)}

    updated = copy.deepcopy(read(source))
    updated["revision"] += 1
    updated["answers"].append({"id": "a-demo-update", "questionId": "q-1",
                               "text": "숙박 일수의 상한을 14박으로 변경합니다.", "status": "answered", "supersedes": "a-1"})
    changed_source = workspace / "source-updated.json"
    write_new(changed_source, updated)
    source_change = {"impact": inspect_impact(workspace, baseline, changed_source),
                     "evidence": inspect_evidence(workspace, evidence)}

    implementation = workspace / "examples/enterprise-ai-web/server.py"
    with implementation.open("a") as stream:
        stream.write("\n# Synthetic demonstration of a file change after testing.\n")
    code_change = {"impact": inspect_impact(workspace, baseline, source),
                   "evidence": inspect_evidence(workspace, evidence)}
    expectations = {
        "initial_binding_unchanged": initial["impact"]["status"] == "UNCHANGED",
        "mapped_tests_passed": evidence["status"] == "PASS",
        "initial_evidence_current": initial["evidence"]["usable_pass"],
        "source_change_requires_review": source_change["impact"]["status"] == "REVIEW_REQUIRED",
        "source_change_does_not_rewrite_test_result": source_change["evidence"]["usable_pass"],
        "code_change_requires_review": code_change["impact"]["status"] == "REVIEW_REQUIRED",
        "code_change_stales_evidence": code_change["evidence"]["freshness"] == "STALE",
    }
    result = {"schema_version": 1, "synthetic_demo": True, "human_approval": False,
              "status": "DEMO_PASS" if all(expectations.values()) else "DEMO_FAILED",
              "draft": draft_result, "tests_count": len(evidence["tests"]),
              "expectations": expectations, "initial": initial,
              "after_interview_change": source_change, "after_code_change": code_change}
    write_new(output / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory; parent must exist")
    args = parser.parse_args()
    try:
        result = run_demo(Path(__file__).resolve().parents[1], args.output)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError):
        parser.exit(1, "Demo failed. Use a new output directory with an existing parent; check repository inputs.\n")
    print(json.dumps({"status": result["status"], "synthetic_demo": True,
                      "tests_count": result["tests_count"], "expectations": result["expectations"],
                      "summary": str(args.output / "summary.json")}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "DEMO_PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
