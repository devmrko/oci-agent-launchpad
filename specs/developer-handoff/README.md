# 다른 개발자나 도구에 변경 작업 넘기기

**변경할 요구, 합격 조건, 관련 코드·테스트 위치를 한 문서에 모아 구현 작업을 전달합니다.** 수신자는 자신의 편집기나 개발 도구로 작업하고, 변경 diff와 실제 검증 결과를 반환할 수 있습니다. 특정 AI 서비스나 API·MCP·웹 형태를 선택할 필요는 없습니다.

## 작업 지시서 만들기

Python 3.12 이상에서 저장소 루트로 이동해 실행합니다. 아래는 아직 적용하지 않은 **박당 12만 원 변경 제안**입니다. 지시서를 만드는 명령은 앱을 수정하거나 테스트를 실행하지 않습니다.

```sh
mkdir -p .run
python3 scripts/developer_handoff.py prepare specs/travel-allowance \
  --requirement REQ-001 --requirement REQ-006 \
  --request '박당 숙박비 한도를 12만 원으로 변경해 주세요.' \
  --acceptance '2박은 240000원이며 웹과 CLI 결과가 같다.' \
  --acceptance '숙박 허용 범위 1~14박과 기존 접근 제어를 유지한다.' \
  --output .run/cost-change
```

출력 폴더에는 두 파일이 생성됩니다.

| 파일 | 역할 |
|---|---|
| `TASK.md` | 현재 요구 본문, 제안한 변경·합격 조건, 관련 구현과 테스트, 반환할 결과 안내 |
| `baseline.json` | 명세에 연결된 파일의 생성 당시 해시, 선택한 요구와 제안 내용 |

소스 코드를 복사하지 않습니다. 수신자는 해당 프로젝트 checkout과 접근 권한을 별도로 확보해야 합니다. 경로는 프로젝트 루트 기준입니다. 현재 명세의 링크가 유효해야 하므로 아직 코드·테스트 연결이 비어 있는 초안은 먼저 보완하세요. 재생성할 때는 새 출력 폴더를 사용합니다.

선택한 실행 명령에 지시서를 전달하려면 [별도 작업 폴더에서 도구 실행하기](../developer-runner/README.md)를 사용할 수 있습니다. 자동 병합·배포는 하지 않습니다.

## 전달 전과 구현을 받은 뒤 확인하기

```sh
python3 scripts/developer_handoff.py check .run/cost-change/baseline.json
```

`UNCHANGED`는 연결 파일이 지시서 생성 당시와 같다는 뜻입니다. 파일이 바뀌거나 현재 연결이 깨지면 `REVIEW_REQUIRED`와 종료 코드 `2`를 반환합니다. 정상적인 구현 변경도 재검토 대상이며, 이것은 변경 실패 판정이 아닙니다.

수신자가 반환한 diff에서 요구·합격 조건·구현·테스트를 검토하고 다음처럼 실제 검증을 실행합니다.

```sh
python3 scripts/spec_evidence.py run specs/travel-allowance --output .run/returned-evidence.json
python3 scripts/spec_evidence.py check .run/returned-evidence.json
```

기존 테스트만 통과해서는 새 조건을 검증했다고 볼 수 없습니다. 새로운 조건의 경계·실패 테스트를 추가하고 `traceability.json`에도 연결해야 합니다. 테스트 근거는 실행한 파일 버전에만 해당하며 고객 승인이나 배포 성공을 뜻하지 않습니다.

## 반환된 구현을 검토 보고서로 모으기

테스트 실행 후 원래 작업 기준과 실행 근거를 함께 지정합니다. 아래 경로는 앞의 명령에서 만든 파일입니다.

```sh
python3 scripts/developer_handoff.py report .run/cost-change/baseline.json \
  --evidence .run/returned-evidence.json \
  --output .run/cost-review
```

새 폴더의 `REVIEW.md`는 원래 요청·합격 조건·변경 파일·테스트 상태를 보여주고, `review.json`은 같은 결과를 도구에서 읽도록 제공합니다. 모든 합격 조건은 체크되지 않은 사람 검토 대기로 남습니다.

| 결과 | 의미 |
|---|---|
| `TESTS_CURRENT_REVIEW_PENDING` / 종료 코드 0 | 현재 연결 파일에 맞는 통과 근거가 있음. 요구 충족 여부는 아직 검토해야 함 |
| `CHECKS_REQUIRED` / 종료 코드 2 | 테스트 근거 누락·실패·오래됨, 요구 삭제 또는 기존 테스트 제거 등을 추가 확인해야 함 |
| 종료 코드 1 | 잘못된 입력·다른 명세의 테스트 근거·기존 출력 경로 등으로 보고서 생성 실패 |

`--evidence`를 생략하면 테스트 근거가 없는 검토 보고서를 만들 수 있습니다. 보고서를 만드는 명령은 테스트를 다시 실행하지 않습니다. `CURRENT`는 파일이 일치한다는 뜻으로, 실패한 테스트도 CURRENT일 수 있습니다. 보고서는 기록된 테스트 결과를 별도로 표시합니다.

테스트 이름 변경이나 다른 요구로의 이동도 기존 연결 제거로 표시합니다. 정당한 변경인지 diff로 확인하세요. 본문 변경은 파일 해시 변화로 확인하며 테스트가 약해졌는지를 자동 판단하지 않습니다. 보고서를 만든 뒤 코드를 수정했다면 새 근거와 새 출력 폴더로 다시 생성합니다. 다른 프로젝트에서는 report에도 `--root`를 지정합니다.

## 다른 프로젝트에서도 사용하기

도구가 있는 Launchpad 경로에서 명령을 실행하고 `--root /path/to/project`를 추가합니다. 명세 폴더와 연결된 구현·테스트 경로는 해당 프로젝트 루트 기준이며, 그 밖의 경로는 거부합니다.

```sh
python3 scripts/developer_handoff.py prepare specs/cost \
  --root /path/to/project \
  --requirement REQ-001 \
  --request '음수 비용을 거부하도록 확장해 주세요.' \
  --acceptance '음수 입력은 오류를 반환하고 양수 합산은 유지한다.' \
  --output .run/external-cost-change

python3 scripts/developer_handoff.py check .run/external-cost-change/baseline.json --root /path/to/project
python3 scripts/spec_evidence.py run specs/cost --root /path/to/project --output .run/external-evidence.json
python3 scripts/spec_evidence.py check .run/external-evidence.json --root /path/to/project
```

출력 경로는 명령을 실행하는 현재 폴더 기준입니다. `/path/to/project`와 `specs/cost`는 실제 경로로 바꾸세요. `--root`를 생략하면 기존처럼 Launchpad 저장소를 사용합니다. 프로젝트에는 현재 도구가 읽는 `spec.md`, `design.md`, `tasks.md`, `traceability.json`이 필요하며 테스트 실행기는 Python unittest를 지원합니다. 임의의 언어·프레임워크를 자동 인식하는 기능은 아닙니다.

## 검증 범위

별도 임시 비용 합산 프로젝트에서 지시서 생성, 변경 감지, 새 음수 입력 테스트 실패, 구현 수정 후 실제 테스트 통과를 검증했습니다. 외부 운영 프로젝트나 다른 사람이 받은 뒤 작업한 결과까지 검증한 것은 아닙니다.

이 도구는 로컬 파일만 작성하고 외부로 전송하지 않습니다. TASK.md에는 요구와 제안 내용이 포함되므로 공유 전에 내용을 확인하세요. 해시는 명세에 연결된 파일 전체를 비교하며 연결하지 않은 의존 파일·환경·요구의 의미적 충분성은 검사하지 않습니다. 지시서와 JSON은 편집 가능하며 서명된 증적이 아닙니다.
