"""Prepare tool-neutral change instructions for an existing spec-linked project."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from check_spec_links import check
from requirement_handoff import read, write_new
from spec_impact import local
from spec_init import line


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
    tests = sorted({(t["path"], t["case"]) for r in selected for t in r["tests"]})
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
    for command in (make, verify):
        command.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.root, args.bundle, args.requirement, args.request, args.acceptance, args.output)
            result = {"status": "PREPARED", "tests_executed": False, "approval_recorded": False}
        else:
            result = inspect(args.root, read(args.baseline))
    except (OSError, ValueError, KeyError, TypeError, SyntaxError):
        parser.exit(1, "Check project paths, requirement IDs, inputs and a new output directory.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "REVIEW_REQUIRED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
