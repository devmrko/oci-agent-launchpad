# 요구사항별 테스트 결과 남기기

검토한 명세를 구현한 뒤, **어떤 요구의 테스트가 통과했는지와 지금 코드에도 그 결과를 참고할 수 있는지** 확인하는 기능입니다. Python 표준 라이브러리와 일반 JSON을 사용하므로 특정 AI 도구나 OCI 계정 없이 실행할 수 있습니다.

예를 들어 출장비 계산 규칙(REQ-001)에 연결된 테스트를 실행한 후 계산 코드를 수정하면, 이전 결과는 `STALE`(코드가 달라져 재실행 필요)로 표시됩니다.

## 바로 실행하기

저장소 루트에서 Python 3.12 이상으로 실행합니다. `.run`은 공개하지 않는 로컬 결과 디렉터리입니다.

```sh
mkdir -p .run
python3 scripts/spec_evidence.py run specs/travel-allowance --output .run/travel-evidence.json
python3 scripts/spec_evidence.py check .run/travel-evidence.json
```

첫 명령은 traceability.json에 연결된 Python unittest를 실제 실행합니다. 같은 테스트가 여러 요구에 연결되어도 한 번만 실행합니다. 예제에서는 OCI를 호출하지 않는 테스트 대역을 사용합니다.

두 번째 명령은 테스트를 다시 실행하지 않고 연결된 명세·설계·작업 목록·구현·테스트 파일의 SHA-256을 비교합니다. 결과 파일을 덮어쓰지 않으므로 재실행할 때는 `travel-evidence-2.json`처럼 새 이름을 사용하세요.

## 결과 읽기

| 항목 | 의미 |
|---|---|
| `status: PASS` | 연결된 모든 테스트가 정상 통과했고 실행 전후 파일이 일치함 |
| `status: NOT_PASSED` | 실패·오류·skip·expected failure·시간 초과 등이 있음 |
| `status: INVALIDATED` | 실행 전후 파일이 달라져 결과를 근거로 사용할 수 없음 |
| `requirements` | 요구 ID별 연결 테스트 판정. 전체 status가 INVALIDATED이면 이 값도 유효한 근거가 아님 |
| `freshness: CURRENT` | 현재 연결 파일이 실행 당시 해시와 같음. 테스트 통과 여부와 별개 |
| `freshness: STALE / INVALID` | 파일이 변경됐거나 연결을 검증할 수 없음 |
| `usable_pass` | 저장된 통과 결과이고 현재 연결 파일과 일치하는지 |

종료 코드는 통과/현재 유효한 통과 `0`, 재검토가 필요한 결과 `2`, 잘못된 입력이나 저장 오류 `1`입니다. 테스트당 제한 시간은 기본 30초이며 `--timeout 10`으로 바꿀 수 있습니다. 상세 실패 메시지는 결과 JSON에 저장하지 않습니다. 원인 분석은 해당 테스트를 직접 실행하세요.

## 전체 흐름에서의 역할

[인터뷰 요구 검토](../interview-handoff/README.md) → [구현 명세와 연결·변경 영향 확인](../change-impact/README.md) → **연결된 테스트 실행 및 결과 보관** 순서입니다. 이번 기능은 구현 명세의 요구 ID와 파일 해시를 기준으로 합니다. 인터뷰 검토 기록의 유효성은 기존 변경 영향 검사로 별도 확인해야 합니다.

`run`은 저장소의 테스트 코드를 실행하므로 신뢰하는 저장소에서 사용하세요. 프로세스 분리는 보안 샌드박스가 아닙니다. 이 결과는 수정 가능한 로컬 JSON이며 서명된 증적이 아닙니다. 연결되지 않은 파일, 설치된 의존성·환경 변화, 테스트의 충분성, 실제 OCI 연동·배포 성공을 보증하지 않습니다. Git 커밋이 같더라도 작업 파일은 다를 수 있어 실제 파일 해시를 기준으로 삼습니다.

다른 프로젝트의 명세와 코드를 검증하려면 run·check 명령에 `--root /path/to/project`를 지정합니다. [작업 전달과 반환된 구현 검증](../developer-handoff/README.md)에 전체 절차가 있습니다.
