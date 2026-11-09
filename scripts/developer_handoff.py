"""Prepare tool-neutral change instructions for an existing spec-linked project."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from check_spec_links import check, test_reference
from requirement_handoff import read, write_new
from spec_impact import local
from spec_init import line
from spec_evidence import inspect as inspect_evidence
from command_evidence import inspect as inspect_command


def prepare(root, bundle, requirements, request, acceptance, output):
    root = Path(root).resolve()
    directory = local(root, bundle)
    request = line(request)
    if not isinstance(acceptance, list) or not 1 <= len(acceptance) <= 100:
        raise ValueError("Provide acceptance criteria")
    acceptance = [line(item) for item in acceptance]
    if not isinstance(requirements, list) or not requirements or len(set(requirements)) != len(requirements):
        raise ValueError("Select unique requirement IDs")
    links = check(root, bundle)
    if not set(requirements) <= set(links["requirements"]):
        raise ValueError("Unknown requirement")
    manifest = read(directory / "traceability.json")
    selected = [r for r in manifest["requirements"] if r["id"] in requirements]
    spec = (directory / "spec.md").read_text()
    sections = re.split(r"(?=^## )", spec, flags=re.M)
    selected_text = [s.strip() for s in sections if any(re.match(r"## " + re.escape(r) + r"\b", s) for r in requirements)]
    source_files = sorted({p for r in selected for p in r["implementation"]})
    tests = sorted({(t["path"], test_reference(t)) for r in selected for t in r["tests"]})
    task = f"# 변경 작업 지시서\n\n{request}\n\n상태: 제안된 작업. 고객 승인·구현·검증 완료를 뜻하지 않습니다.\n"
    task += "\n## 현재 요구\n\n" + "\n\n".join(s.replace("## ", "### ", 1) for s in selected_text) + "\n"
    task += "\n## 변경 후 합격 조건 (작성자 제안)\n\n" + "".join(f"- {s}\n" for s in acceptance)
    task += "\n## 살펴볼 구현 파일\n\n" + "".join(f"- `{p}`\n" for p in source_files)
    task += "\n## 기존 테스트와 추가 검증\n\n" + "".join(f"- `{p}` — `{c}`\n" for p, c in tests)
    task += "\n기존 테스트를 유지하고 변경된 합격 조건의 경계·실패 테스트를 보완하세요. 기존 테스트 통과만으로 새 요구를 충족했다고 판단하지 않습니다.\n"
    task += f"\n## 작업 자료와 반환할 결과\n\n프로젝트 checkout이 별도로 필요합니다. 모든 경로는 프로젝트 루트 기준입니다. `{bundle}/spec.md`, `{bundle}/design.md`, `{bundle}/tasks.md`, `{bundle}/traceability.json`을 함께 검토하세요.\n\n"
    task += "변경 diff, 실행한 검증 명령·결과, 미확인 사항을 반환하세요. 명세·설계·작업 기록과 실제 코드·테스트 연결을 함께 갱신하세요. 제공 형태와 개발 도구는 프로젝트에 맞게 선택합니다. 지시서 생성은 명령 실행·배포를 승인하지 않습니다.\n"
    result = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "bundle": str(bundle), "requirements": requirements, "request": request,
              "acceptance": acceptance, "files": links["files"], "selected_mapping": selected,
              "tests_executed": False, "approval_recorded": False}
    if Path(output).is_symlink():
        raise ValueError("Output must not be a symlink")
    Path(output).mkdir(mode=0o700)
    (Path(output) / "TASK.md").write_text(task, encoding="utf-8")
    write_new(Path(output) / "baseline.json", result)
    return result


def inspect(root, baseline):
    if baseline.get("schema_version") != 1 or not isinstance(baseline.get("files"), dict) or not baseline["files"]:
        raise ValueError("Invalid baseline")
    local(root, baseline["bundle"])
    for name in baseline["files"]:
        local(root, name)
    try:
        current = check(root, baseline["bundle"])["files"]
    except (OSError, ValueError, KeyError, TypeError, SyntaxError):
        return {"status": "REVIEW_REQUIRED", "reason": "current_links_invalid", "tests_executed": False}
    changes = sorted(p for p in current.keys() | baseline["files"].keys() if current.get(p) != baseline["files"].get(p))
    return {"status": "REVIEW_REQUIRED" if changes else "UNCHANGED", "changed_files": changes,
            "tests_executed": False, "implementation_accepted": False}



def report(root, baseline, evidence, output, command_evidence=None):
    changes = inspect(root, baseline)
    request = line(baseline["request"])
    acceptance = [line(item) for item in baseline["acceptance"]]
    selected = baseline["requirements"]
    if not acceptance or not isinstance(selected, list) or not selected:
        raise ValueError("Missing requested requirements or criteria")
    directory = local(root, baseline["bundle"])
    reasons = []
    command_evidence = command_evidence or []
    command_states = []
    current = None
    missing, removed = [], []
    try:
        current = check(root, baseline["bundle"])
        missing = sorted(set(selected) - set(current["requirements"]))
        records = read(directory / "traceability.json")["requirements"]
        current_tests = {(r["id"], t["path"], test_reference(t)) for r in records for t in r["tests"]}
        old_tests = {(r["id"], t["path"], test_reference(t)) for r in baseline["selected_mapping"] for t in r["tests"]}
        removed = [{"requirement": rid, "path": path, "case": case} for rid, path, case in sorted(old_tests - current_tests)]
        if missing:
            reasons.append("selected_requirements_missing")
        if removed:
            reasons.append("previous_tests_removed_or_reassigned")
    except (OSError, KeyError, TypeError, SyntaxError, ValueError):
        reasons.append("current_links_invalid")
    evidence_state = {"freshness": "MISSING", "usable_pass": False}
    if evidence is None:
        if not command_evidence:
            reasons.append("test_evidence_missing")
    else:
        if local(root, evidence["bundle"]) != directory:
            raise ValueError("Evidence belongs to a different specification")
        evidence_state = inspect_evidence(root, evidence)
        if not evidence_state["usable_pass"] or evidence.get("tests_executed") is not True:
            reasons.append("test_evidence_not_current_pass")
        if not all(evidence.get("requirements", {}).get(rid) == "PASS" for rid in selected):
            reasons.append("selected_requirements_not_passed")
    referenced, covered = set(), set()
    for item in command_evidence:
        state = inspect_command(root, item)
        plan = read(local(root, item["plan"]))
        if local(root, plan["spec"]) != directory / "spec.md":
            raise ValueError("Command evidence belongs to a different specification")
        if item.get("requirements") != plan.get("requirements"):
            reasons.append("command_requirement_references_changed")
        referenced.update(plan["requirements"])
        covered.update(item["files"])
        if not state["usable_command_success"]:
            reasons.append("command_evidence_not_current_success")
        command_states.append({**state, "command": item.get("command", []),
                               "recorded_status": item.get("status"), "exit_code": item.get("exit_code"),
                               "recorded_at": item.get("recorded_at"), "requirements": item.get("requirements"),
                               "stable_during_run": item.get("stable_during_run"), "plan": item["plan"]})
    if command_evidence:
        if not set(selected) <= referenced:
            reasons.append("command_requirement_references_missing")
        if current is None or not set(current["files"]) <= covered:
            reasons.append("command_file_coverage_incomplete")
    reasons = list(dict.fromkeys(reasons))
    ready = "TESTS_CURRENT_REVIEW_PENDING" if evidence is not None else "COMMANDS_CURRENT_REVIEW_PENDING"
    result = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "status": "CHECKS_REQUIRED" if reasons else ready,
              "command_evidence": command_states, "requirements_verified": False,
              "request": request, "requirements": selected, "changes": changes,
              "evidence": evidence_state, "evidence_recorded_at": evidence.get("recorded_at") if evidence else None,
              "reasons": reasons, "missing_requirements": missing,
              "removed_tests": removed,
              "acceptance": [{"text": item, "status": "HUMAN_REVIEW_PENDING"} for item in acceptance],
              "tests_executed": False, "implementation_accepted": False, "approval_recorded": False}
    content = f"# 구현 반환 검토 보고서\n\n{request}\n\n상태: `{result['status']}`. 모든 합격 조건은 사람 검토 대기 상태입니다.\n"
    content += "\n## 요청한 합격 조건\n\n" + "".join(f"- [ ] {item}\n" for item in acceptance)
    content += "\n## 연결 파일의 변경\n\n"
    if changes["status"] == "UNCHANGED":
        content += "연결 파일은 작업 전달 당시와 같습니다. 변경 요청이 실제 반영됐는지 확인하세요.\n"
    else:
        content += "".join(f"- `{name}`\n" for name in changes.get("changed_files", [])) or "현재 연결을 검사할 수 없습니다. review.json을 확인하세요.\n"
    content += f"\n## 요구별 테스트 근거\n\n현재 파일과 비교한 상태: `{evidence_state['freshness']}`\n\n"
    content += f"기록된 테스트 결과: `{evidence_state.get('recorded_status', 'MISSING')}`\n\n"
    if command_states:
        content += "\n## 테스트 명령 실행 근거\n\n명령 성공은 요구별 테스트 통과 판정이 아닙니다. 요구 충족 여부는 사람 검토 대기입니다.\n\n"
        for entry in command_states:
            content += (f"- 명령(argv): `{json.dumps(entry['command'], ensure_ascii=False)}`\n"
                        f"  결과: `{entry['recorded_status']}`, 종료 코드: `{entry['exit_code']}`, "
                        f"현재성: `{entry['freshness']}`, 실행 중 파일 일치: `{entry['stable_during_run']}`\n")
    content += "\n추가 확인 항목: " + (", ".join(reasons) if reasons else "자동 검사 범위에서 없음") + "\n"
    if removed:
        content += "\n제거되거나 다른 요구로 이동한 기존 테스트:\n\n" + "".join(f"- {t['requirement']}: `{t['path']}` — `{t['case']}`\n" for t in removed)
    content += "\n## 검토할 내용\n\n변경 diff와 새 조건의 경계·실패 테스트를 확인하세요. 테스트 통과는 요구 충족·고객 승인·배포 성공을 의미하지 않습니다. 보고서는 테스트를 재실행하지 않았으며 연결되지 않은 파일과 환경 변화는 검사 범위 밖입니다.\n"
    if Path(output).is_symlink():
        raise ValueError("Output must not be a symlink")
    Path(output).mkdir(mode=0o700)
    (Path(output) / "REVIEW.md").write_text(content, encoding="utf-8")
    write_new(Path(output) / "review.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("prepare")
    make.add_argument("bundle")
    make.add_argument("--requirement", action="append", required=True)
    make.add_argument("--request", required=True)
    make.add_argument("--acceptance", action="append", required=True)
    make.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser("check")
    verify.add_argument("baseline", type=Path)
    review = commands.add_parser("report")
    review.add_argument("baseline", type=Path)
    review.add_argument("--evidence", type=Path)
    review.add_argument("--command-evidence", type=Path, action="append", default=[])
    review.add_argument("--output", required=True, type=Path)
    for command in (make, verify, review):
        command.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.root, args.bundle, args.requirement, args.request, args.acceptance, args.output)
            result = {"status": "PREPARED", "tests_executed": False, "approval_recorded": False}
        elif args.command == "report":
            result = report(args.root, read(args.baseline), read(args.evidence) if args.evidence else None, args.output,
                            [read(path) for path in args.command_evidence])
        else:
            result = inspect(args.root, read(args.baseline))
    except (OSError, ValueError, KeyError, TypeError, SyntaxError):
        parser.exit(1, "Check project paths, requirement IDs, inputs and a new output directory.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] in {"REVIEW_REQUIRED", "CHECKS_REQUIRED"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
