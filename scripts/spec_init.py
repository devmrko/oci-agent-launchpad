"""Create a portable specification draft from directly supplied requirements."""
import argparse
import json
from pathlib import Path
import sys

from requirement_handoff import write_new
from spec_impact import local


def line(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000 or any(ord(c) < 32 for c in value):
        raise ValueError("Use nonempty single-line text of at most 2000 characters")
    return value


def initialize(root, output, title, purpose, requirements):
    title, purpose = line(title), line(purpose)
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 100:
        raise ValueError("Provide 1 to 100 requirements")
    requirements = [line(item) for item in requirements]
    if len(set(requirements)) != len(requirements):
        raise ValueError("Duplicate requirements")
    if (Path(root) / output).is_symlink():
        raise ValueError("Output must not be a symlink")
    destination = local(root, output)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Output must be a new directory")
    records = [{"id": f"REQ-{index:03}", "implementation": [], "tests": []}
               for index in range(1, len(requirements) + 1)]
    spec = f"# {title}\n\n{purpose}\n\n상태: 초안. 요구 검토·합격 조건 작성·구현·테스트는 미완료입니다.\n"
    for record, requirement in zip(records, requirements):
        spec += f"\n## {record['id']}\n\n{requirement}\n\n합격 조건: 미작성 — 입력, 기대 결과, 실패 조건을 구체적으로 작성하세요.\n"
    design = f"# {title} 설계 초안\n\n목적: {purpose}\n\n구현 전에 아래 항목을 작성하고 요구와 연결하세요.\n\n"
    design += "- 입력과 출력: 미정\n- 구성요소와 역할: 미정\n- 데이터·권한·오류 처리: 미정\n- AI 및 OCI 필요 여부와 선택 이유: 미정\n- 배포·운영 범위: 미정\n"
    for record in records:
        design += f"\n## {record['id']} 설계\n\n구현 방식과 선택 이유: 미작성\n"
    tasks = "# 구현과 검증 작업\n\n완료한 작업만 체크하고 검증 명령·결과·범위를 기록하세요.\n\n"
    for record in records:
        rid = record['id']
        tasks += f"- [ ] {rid}: 요구와 합격 조건 검토\n- [ ] {rid}: 설계 작성 및 구현\n- [ ] {rid}: 테스트 작성 후 traceability.json에 실제 파일·테스트 이름 연결\n"
    tasks += "- [ ] 링크 검사와 실제 테스트 실행, 결과 검토\n\n## 검증 기록\n\n아직 실행하지 않았습니다.\n"
    destination.mkdir(mode=0o700)
    for name, content in (("spec.md", spec), ("design.md", design), ("tasks.md", tasks)):
        (destination / name).write_text(content, encoding="utf-8")
    write_new(destination / "traceability.json", {"schema_version": 1, "requirements": records})
    return {"status": "DRAFT", "bundle": str(output), "requirements": len(records),
            "tests_executed": False, "review_recorded": False,
            "next_steps": ["Review requirements and acceptance criteria", "Write design, implementation and tests",
                           "Fill traceability.json with repository-relative paths", "Check links and run test evidence"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New repository-relative directory; parent must exist")
    parser.add_argument("--title", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--requirement", action="append", required=True)
    args = parser.parse_args()
    try:
        result = initialize(Path(__file__).resolve().parents[1], args.output, args.title, args.purpose, args.requirement)
    except (OSError, ValueError, TypeError):
        parser.exit(1, "Cannot create draft: check single-line inputs and a new repository-local output directory.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
