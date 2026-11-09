# 작업 지시서를 실행 명령에 전달하기

**선택한 개발 도구를 별도 작업 폴더에서 실행하고, 변경 파일과 diff를 돌려받습니다.** 사용자는 명령을 직접 지정하며 특정 AI 제품이나 앱 제공 방식을 요구하지 않습니다. 원본 프로젝트로의 자동 반영·병합·배포는 하지 않습니다.

자동 검증 범위는 macOS·Linux의 작은 Python 프로젝트와 결정적인 로컬 테스트 어댑터입니다. 별도로 [설치된 Codex CLI로 구현하고 검토·반영한 사례](codex-integration.md)가 있습니다. Codex 어댑터는 선택 사항이며 인증은 설치된 CLI가 담당합니다.

## 실행 전 준비

Python 3.12 이상, 명세에 연결된 소스·테스트, [개발자 작업 지시서](../developer-handoff/README.md)가 필요합니다. 지시서 생성 후 연결 파일을 바꿨다면 최신 기준으로 새 지시서를 만드세요.

다음 명령의 도구 경로와 옵션은 **설치한 실제 도구에 맞게 바꿔야 합니다**. Launchpad가 도구를 자동 설치하거나 인증하지 않습니다.

```sh
python3 scripts/developer_runner.py .run/cost-change \
  --output .run/cost-execution --timeout 300 \
  -- /absolute/path/to/development-tool --task-file '{task}'
```

`--` 앞은 실행기 옵션, 뒤는 실제 실행 파일과 인자입니다. `{task}`는 복사한 TASK.md의 절대 경로, `{workspace}`는 작업 폴더의 절대 경로로 치환됩니다. 현재 디렉터리는 workspace입니다. 셸을 거치지 않아 파이프·리다이렉션·`$()` 등을 명령 문법으로 처리하지 않습니다. 상대 실행 파일 경로는 workspace 기준이므로 도구는 절대 경로나 PATH에 있는 이름으로 지정하세요.

다른 프로젝트는 `--root /path/to/project`를 추가합니다. 복사 범위는 baseline.json에 연결된 파일뿐입니다. Git 이력·미연결 의존 파일·설정은 자동 복사하지 않습니다. 개발 도구가 이외의 파일을 필요로 한다면 이 방식의 적용 범위를 먼저 검토하세요.

## 반환되는 결과

| 파일 | 내용 |
|---|---|
| `workspace/` | 연결 파일의 복사본과 실행 도구가 만든 변경 |
| `TASK.md` | 전달한 작업 지시서 |
| `status.json` | 실행 중 RUNNING, 종료 후 최종 상태 |
| `run.json` | 종료 코드, 변경 파일과 전후 해시, 수집 상태 |
| `changes.diff` | 텍스트 변경 diff. 바이너리는 변경 사실만 표시 |

`COMMAND_SUCCEEDED`는 명령이 종료 코드 0으로 끝났다는 뜻이며 구현 완료·테스트 통과가 아닙니다. 실패는 `COMMAND_FAILED`, 시간 초과는 `TIMED_OUT`, 실행 실패는 `START_FAILED`, Ctrl+C는 `INTERRUPTED`로 구분합니다. 출력 수집 실패는 `COLLECTION_FAILED`입니다. CLI는 명령 성공과 수집 완료일 때만 0, 실행/수집 문제는 2, 준비 오류는 1을 반환합니다.

기존 출력 폴더는 덮어쓰지 않습니다. stdout·stderr와 실행 인자는 결과 파일에 저장하지 않습니다. 오류 상세 분석이 필요하면 사용한 도구 자체의 진단 방법을 사용하세요. 변경 diff에는 코드 내용이 포함되므로 외부 공유 전에 검토하세요.

## 반환된 구현 검증

예를 들어 출장비 명세라면 실행 도구가 끝난 후 Launchpad의 검증기를 사용합니다.

```sh
python3 scripts/spec_evidence.py run specs/travel-allowance \
  --root .run/cost-execution/workspace --output .run/cost-returned-evidence.json
python3 scripts/developer_handoff.py report .run/cost-change/baseline.json \
  --root .run/cost-execution/workspace \
  --evidence .run/cost-returned-evidence.json --output .run/cost-return-review
```

새 합격 조건의 테스트를 포함하고 diff·결과를 검토한 후 원본 반영 여부를 결정합니다. 테스트와 보고서가 자동 승인하거나 원본에 변경을 적용하지 않습니다.

## 실행 경계와 검증한 범위

작업 폴더 분리는 보안 샌드박스가 아닙니다. 선택한 명령은 현재 계정의 권한과 환경 변수를 가지며 네트워크나 폴더 밖 파일에 접근할 수도 있습니다. 실행기가 원본에 자동 적용하지 않는다는 뜻이지, 임의 프로그램의 원본 접근을 차단한다는 뜻은 아닙니다. 명시적으로 실행하기로 정한 도구에 사용하세요.

시간 초과·종료 시 같은 프로세스 그룹의 자식 프로세스도 정리합니다. 자체적으로 그룹을 벗어나는 프로세스까지 격리하지 않습니다. 심볼릭 링크·비정규 파일, 파일당 1MiB·총 8MiB·200개를 넘는 출력은 수집하지 않습니다. `.git`과 `__pycache__`는 diff 대상에서 제외합니다.

자동 테스트에서는 음수 입력 거부 조건을 충족하지 못하는 비용 합산 코드에 지시서를 전달하고, 로컬 테스트 어댑터가 복사본을 수정한 뒤 실제 테스트가 실패에서 통과로 바뀌는지 확인합니다. 원본 보존, 실패·시간 초과·실행 파일 누락, 오래된 기준 거부, 기존 결과 보호, 셸 구문 미해석도 확인합니다. 이 결과를 실제 AI 개발 도구의 구현 품질로 확대 해석하지 않습니다.
