# 프로젝트의 기존 테스트 명령 연결하기

**프로젝트에서 쓰던 테스트 명령을 실행하고, 어떤 파일 버전에서 성공하거나 실패했는지 기록합니다.** Python unittest 연결 파일을 만들지 않고 `pytest`, `npm test`, `mvn test`처럼 설치된 도구의 명령을 지정할 수 있습니다. 실행기는 Python 표준 라이브러리만 사용하며, 대상 도구와 프로젝트 의존성은 미리 준비해야 합니다.

이 기록은 **명령의 종료 결과**입니다. 테스트 수·skip·요구별 충족 여부를 파싱하지 않습니다. 테스트를 하나도 실행하지 않고 0으로 끝난 명령도 성공으로 기록될 수 있으므로 기존 테스트 도구의 설정과 보고서를 함께 확인하세요.

## 먼저 Hello Agent로 확인

macOS·Linux / Python 3.12 이상에서 Launchpad 저장소 루트로 이동해 실행합니다. 이 예제는 추가 패키지·OCI 계정이 필요하지 않습니다.

```sh
mkdir -p .run
python3 -S scripts/command_evidence.py run specs/command-evidence/hello-plan.json \
  --output .run/hello-command.json \
  -- python3 -S -m unittest discover -s examples/hello-agent -p test_agent.py
python3 -S scripts/command_evidence.py check .run/hello-command.json
```

첫 명령은 `COMMAND_SUCCEEDED`, `exit_code: 0`, `stable_during_run: true`를 반환합니다. 두 번째는 명령을 실행하지 않고 파일을 비교해 `CURRENT`, `usable_command_success: true`를 반환합니다. 두 결과 모두 `requirements_verified: false`입니다.

`--` 앞은 실행기 옵션이고 뒤는 실제 명령과 인자입니다. `--timeout 60`으로 제한 시간을 정할 수 있으며 기본은 300초입니다. 출력 파일은 덮어쓰지 않으므로 재실행 시 새 이름을 사용합니다.

## 자신의 프로젝트에서 쓰기

프로젝트 루트에 아래처럼 `checks.json`을 작성합니다. 경로·요구 ID는 실제 파일에 맞춰 바꿔야 합니다.

```json
{
  "schema_version": 1,
  "spec": "specs/search/spec.md",
  "requirements": ["REQ-001"],
  "files": ["src/search.js", "test/search.test.js", "package.json", "package-lock.json"]
}
```

명세에는 `## REQ-001 ...` 형태의 요구 제목이 있어야 합니다. `requirements`는 실행과 관련 있다고 지정한 요구이며 충족 판정이 아닙니다. `files`에는 구현·테스트·설정·잠금 파일 등 결과에 영향을 주는 파일을 빠짐없이 지정하세요. 계획과 명세는 자동으로 해시에 포함됩니다. 와일드카드·디렉터리·심볼릭 링크·프로젝트 밖 경로는 지원하지 않습니다.

Launchpad 저장소 루트에서 다음처럼 실행합니다. 실제 명령의 작업 디렉터리는 `--root`입니다. 생략하면 **현재 터미널 폴더**를 사용합니다.

```sh
python3 -S scripts/command_evidence.py run checks.json \
  --root /path/to/project --output .run/project-command.json -- npm test
python3 -S scripts/command_evidence.py check .run/project-command.json --root /path/to/project
```

pytest 프로젝트라면 `-- /absolute/path/to/venv/bin/python -m pytest`, Maven 프로젝트라면 `-- mvn test`처럼 명시적으로 지정합니다. 실행기가 도구를 설치하거나 테스트 프레임워크를 자동 판별하지 않습니다. 기존 unittest 요구별 검증을 사용 중이면 [요구별 테스트 근거](../test-evidence/README.md)를 계속 사용할 수 있습니다.

## 결과 해석

| 결과 | 의미 |
|---|---|
| `COMMAND_SUCCEEDED` | 명령이 종료 코드 0으로 종료 |
| `COMMAND_FAILED` | 명령이 0이 아닌 코드로 종료 |
| `TIMED_OUT` / `START_FAILED` / `INTERRUPTED` | 시간 초과 / 프로세스 시작 실패 / Ctrl+C |
| `stable_during_run: false` | 실행 중 계획·대상 파일이 변경되거나 사라짐. 성공 종료여도 유효한 근거로 쓰지 않음 |
| `CURRENT` / `STALE` / `INVALID` | 파일이 실행 전과 같음 / 달라짐 / 현재 계획·파일을 확인할 수 없음 |

CLI 종료 코드는 파일 변화 없는 명령 성공 또는 유효한 성공 확인 시 0, 실행 실패·오래된 근거 등은 2, 잘못된 입력·출력 경로는 1입니다. 명령 실행 중 프로세스가 강제로 종료되면 결과가 `RUNNING`에 남을 수 있으며 완료 근거로 사용하지 않습니다.

계획 파일은 4MiB 이하, 지정 파일은 최대 200개·각 8MiB 이하입니다. 명령 인자는 결과 JSON에 저장하므로 비밀값을 넣지 마세요. stdout·stderr는 저장하지 않습니다. 실패 원인은 프로젝트의 테스트 보고서를 확인하거나 같은 명령을 직접 실행해 살펴보세요.

현재 계정의 권한과 환경 변수를 상속합니다. 명령을 셸 문자열로 해석하지 않지만 `npm` 등 도구 자체가 실행하는 스크립트는 그대로 실행됩니다. 실행 환경 격리·의존성 설치·비밀값 차단 기능은 아닙니다. 완료·시간 초과 시 같은 프로세스 그룹을 정리하며 그룹을 벗어난 자식 프로세스까지 격리하지 않습니다.

지정하지 않은 파일·설치 패키지·환경 변수 변화는 감지하지 않습니다. 결과는 서명된 증거가 아닙니다. 기존 `spec_evidence`의 `--evidence`와 구분하여 검토 보고서에 `--command-evidence`로 첨부할 수 있습니다. 요구별 합격이나 고객 승인으로 자동 변환하지 않습니다.

## 실제 검증 범위

2026-11-10 macOS / Python 3.15.0에서 Hello Agent unittest 명령 성공과 파일 일치를 확인했습니다. 별도 합성 Node.js 프로젝트에서는 Node 26.12.0 / npm 11.20.0의 실제 `npm test` 성공, 테스트 변경 후 기존 근거 `STALE`, 실패 테스트의 종료 코드 1 기록을 확인했습니다. pytest·Maven 프로젝트의 실제 실행은 이번에 검증하지 않았습니다.

자동 검사에서는 성공·실패·시간 초과·없는 실행 파일·실행 중 파일 변경·파일 삭제·계획 변경·잘못된 경로와 요구·심볼릭 링크·기존 결과 보호·셸 구문 미해석을 확인합니다. [설계와 경계](design.md)

## 변경 검토 보고서에 연결

기존에 생성한 작업 지시서의 `baseline.json`과 명령 결과를 지정합니다. `--command-evidence`를 반복해 여러 결과를 첨부하거나 기존 요구별 `--evidence`와 함께 사용할 수 있습니다.

```sh
python3 -S scripts/developer_handoff.py report .run/hello-task/baseline.json \
  --command-evidence .run/hello-command.json --output .run/hello-command-review
```

`.run/hello-task`는 [작업 지시서 생성](../developer-handoff/README.md)에서 먼저 준비해야 합니다. 외부 프로젝트이면 report에도 같은 `--root`를 지정합니다. 보고서는 요청·변경 파일·명령과 종료 코드·현재 파일 일치 여부를 함께 보여주며 명령을 재실행하지 않습니다.

- 명령 근거만 유효하면 `COMMANDS_CURRENT_REVIEW_PENDING`입니다. 요구별 테스트 통과를 뜻하지 않습니다.
- 요구별 테스트 근거까지 유효하면 기존 `TESTS_CURRENT_REVIEW_PENDING`을 유지합니다.
- 첨부한 명령 중 실패·오래됨·실행 중 변경이 있거나, 요청 요구 참조·현재 명세 연결 파일의 해시 범위가 빠지면 `CHECKS_REQUIRED`입니다.
- 다른 명세의 결과는 입력 오류로 거부합니다. 모든 합격 조건과 승인은 사람 검토 대기로 남습니다.

`prepare`는 아래의 `command_plan` 연결도 지원합니다. 테스트 파일의 언어를 해석하지 않고 파일·명세·계획 연결을 검사합니다. 실제 테스트 실행 명령은 사용자가 별도로 지정합니다.

## unittest 없이 작업 지시서부터 시작하기

`traceability.json`의 테스트 항목에서 `case` 대신 `command_plan`을 지정합니다. 둘을 함께 쓰면 오류입니다.

```json
{
  "requirements": [{
    "id": "REQ-001",
    "implementation": ["cost.cjs"],
    "tests": [{"path": "cost.test.cjs", "command_plan": "checks.json"}]
  }]
}
```

`checks.json`은 앞서 설명한 실행 계획입니다. 같은 명세와 요구 ID를 참조하고 해당 구현·테스트 파일을 포함해야 합니다. 계획에 열거한 의존·설정 파일도 작업 기준 해시와 복사 대상에 포함됩니다. 검토 보고서에 사용할 때는 명세·설계·작업·연결 파일 전체도 계획에 포함하세요. [Node.js 예제 계획](node-example/checks.json)이 실제 형식입니다.

작업 지시서·변경 영향 결과에서 `command:checks.json`은 실행 계획의 참조를 뜻합니다. 기존 JSON 결과의 `case` 표시 필드에도 이 문자열이 사용되며 unittest 메서드가 아닙니다. 계획 참조가 제거되거나 변경되면 기존 테스트 연결 변경으로 표시합니다. `spec_evidence.py run`은 명령 항목을 자동 실행하거나 건너뛰지 않고 거부하므로 `command_evidence.py run`으로 실행하세요.

### Node.js에서 전체 흐름 재현

Node.js와 npm이 설치된 macOS·Linux에서 Launchpad 루트 기준으로 실행합니다. 예제는 추가 패키지를 설치하지 않습니다. 작은 합성 검증 프로젝트이며 초기 구현에는 의도적으로 음수 검사가 빠져 있습니다.

```sh
node_project="$(mktemp -d /tmp/launchpad-node.XXXXXX)"
cp -R specs/command-evidence/node-example/. "$node_project/"
mkdir -p .run
python3 -S scripts/developer_handoff.py prepare specs/cost \
  --root "$node_project" --requirement REQ-001 \
  --request '음수 비용을 거부하도록 구현한다.' \
  --acceptance '음수이면 RangeError이고 양수와 0의 합산은 유지한다.' \
  --output .run/node-task
python3 -S scripts/command_evidence.py run checks.json --root "$node_project" \
  --output .run/node-red.json -- npm test
```

마지막 명령의 **종료 코드 2, COMMAND_FAILED**는 예상된 실패입니다. 결과를 확인한 다음 구현 패치를 적용합니다.

```sh
git -C "$node_project" apply --check "$node_project/fix.patch"
git -C "$node_project" apply "$node_project/fix.patch"
python3 -S scripts/command_evidence.py run checks.json --root "$node_project" \
  --output .run/node-green.json -- npm test
python3 -S scripts/developer_handoff.py report .run/node-task/baseline.json \
  --root "$node_project" --command-evidence .run/node-green.json \
  --output .run/node-review
```

`COMMAND_SUCCEEDED`와 `COMMANDS_CURRENT_REVIEW_PENDING`이 나오고 보고서에 `cost.cjs` 변경이 표시됩니다. 요구 충족·고객 승인은 사람 검토 대기로 남습니다. 재실행에는 새 출력 이름을 사용하세요.

2026-11-10 macOS / Node 26.12.0 / npm 11.20.0에서 이 실패→수정→통과→보고서 흐름을 실제로 확인했습니다. 자동 Python 검사는 명령 계획 기반 작업 전달·잘못된 연결·계획 참조 변경·unittest 실행기의 명령 항목 거부를 검사합니다. Node 실제 실행은 이 로컬 확인 범위이며 현재 CI의 필수 환경으로 추가하지 않았습니다.
