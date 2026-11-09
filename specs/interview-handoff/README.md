# 인터뷰 근거를 요구 초안과 검토 기록으로 연결하기

인터뷰 답변을 가져와 요구 초안으로 정리하고, 사람이 원문과 대조한 기록을 남깁니다. 요구가 바뀌었는데 과거 검토를 그대로 완료로 표시하는 일을 줄이기 위한 도구입니다. Python 표준 라이브러리만 사용하며 특정 챗봇·IDE·OCI 계정이 필요하지 않습니다.

현재 제공하는 것은 **원문을 옮긴 초안, 근거 참조, 자기 기재 검토 기록, 변경 후 재검토 판정**입니다. 답변을 자동 분석해 완성된 명세를 만들거나 고객 합의를 인증하는 기능은 아닙니다.

## 합성 예제로 시작하기

저장소 최상위에서 실행합니다. 아래 예제는 가상의 답변과 검토자이며 실제 고객 승인 기록이 아닙니다.

```sh
mkdir -p .run
python3 scripts/requirement_handoff.py draft \
  --source specs/interview-handoff/interview.example.json \
  --output .run/my-sdd-draft
```

출력은 `DRAFT`, 요구 2개, 미정 1개입니다. 출력 폴더가 이미 있으면 실패합니다. 다시 만들 때는 다른 이름을 사용해 이전 자료를 보존하세요.

| 생성 파일 | 역할 |
|---|---|
| `source.json` | 가져온 인터뷰 snapshot. 원문과 정정 이력을 보존합니다 |
| `requirements.json` | 요구 ID, 편집할 요구 문장, 근거 답변 ID, 미정 질문 ID |
| `reviews/*.json` | 검토 시점의 내용 해시와 검토자 기재값. 새 기록을 추가하며 이전 파일을 덮어쓰지 않습니다 |

`requirements.json`의 요구 문장을 편집기로 다듬고 `source.json`의 답변 ID를 따라 원문을 확인합니다. 범위·성공 조건이 빠져 있으면 인터뷰를 보완합니다. 자동으로 붙은 REQ 번호는 이 초안 안에서의 번호이며, 다른 업무 명세의 같은 번호와 동일한 요구라는 뜻은 아닙니다.

합성 자료로 검토 기록 기능을 시험할 때는 다음을 실행합니다. 실제 업무에서는 해당 검토자가 내용을 검토한 뒤 기록해야 합니다.

```sh
python3 scripts/requirement_handoff.py record-review .run/my-sdd-draft \
  --requirement REQ-001 --reviewer synthetic-demo-reviewer
python3 scripts/requirement_handoff.py status .run/my-sdd-draft \
  --source specs/interview-handoff/interview.example.json
```

REQ-001은 `REVIEW_RECORDED`, REQ-002는 `DRAFT`로 표시됩니다. 검토 기록은 업무 합격·배포 승인이나 인증된 고객 서명이 아니며 `identity_verified=false`를 반환합니다.

## 답변이나 요구가 바뀌면

- 요구 문장을 수정한 뒤 `status`를 실행하면 해당 검토 기록은 `REVIEW_REQUIRED`가 됩니다. 수정한 내용을 검토한 뒤 새 기록을 추가합니다.
- 최신 인터뷰 export를 `status --source 최신파일.json`으로 전달하면 이전 snapshot과 비교합니다. 다른 프로젝트나 더 낮은 revision은 거부합니다.
- 인터뷰 snapshot이 달라지면 모든 요구를 보수적으로 재검토 대상으로 표시합니다. 어떤 답변 변경이 어떤 요구에만 영향을 주는지 정밀 분석하는 기능은 아직 없습니다.
- `--source` 없이 검사하면 캡처된 snapshot만 확인했다는 `captured_snapshot_only` 범위를 반환합니다. 최신 인터뷰까지 확인했다고 표시하지 않습니다.
- 답변이 정정되었다면 최신 파일로 **새 출력 폴더**를 생성하고 기존 명세와 비교합니다. 서로 다른 초안의 REQ 번호는 자동 병합하지 않습니다.

## 기존 인터뷰 화면과 직접 작성한 JSON 사용

기존 인터뷰 export의 `schemaVersion`, `id`, `revision`, `questions`, `answers` 구조를 읽습니다. 화면 없이 [입력 예제](interview.example.json)를 복사해 직접 작성할 수도 있습니다. 질문·답변 ID는 중복될 수 없고, 답변은 존재하는 질문을 참조해야 합니다. 같은 질문의 정정은 `supersedes`에 직전 답변 ID를 넣고 뒤에 추가합니다. `deferred` 답변은 요구로 승격하지 않습니다.

입력 형식 호환은 자동화 시험으로 확인했으며 기존 인터뷰 UI에서 export 버튼을 눌러 끝까지 이어가는 통합 시험은 미실행입니다. 입력의 추가 필드도 원본 snapshot에 보존됩니다. 실제 인터뷰 원문이 포함되므로 출력 폴더를 자동 커밋하거나 공개하지 마세요. 이 도구는 내용을 외부로 전송하거나 비밀값을 자동 제거하지 않습니다.

## 구현과 테스트로 이어가기

검토한 요구를 [출장비 명세](../travel-allowance/spec.md)처럼 성공 조건이 있는 문서로 정리합니다. 요구별로 확인한 근거 ID를 함께 남기고, 설계·작업·테스트 연결은 [SDD 따라하기](../travel-allowance/README.md)의 방식으로 이어갑니다. 기존 명세에 반영할 때는 내용과 ID를 사람이 대조하며, 이 도구가 코드나 배포 설정을 자동 변경하지 않습니다.

```sh
python3 -m unittest discover -s scripts -p 'test_requirement_handoff.py'
```

2026년 11월 9일 테스트 7건과 합성 CLI의 초안 생성→검토 기록→상태 조회를 확인했습니다. 요구 수정·source 정정 시 재검토, 다른 프로젝트·위조 근거·중복 답변 거부, 미정 유지, 기존 출력 보호를 시험했습니다. 설계와 경계는 [구현 전 설계](design.md)에 있습니다.
