# 자신의 요구로 새 명세 시작하기

**만들고 싶은 기능을 직접 입력하면 요구 명세·설계 초안·작업 목록·코드와 테스트 연결 파일을 생성합니다.** 데모를 살펴본 개발자가 자신의 기능을 시작할 때 사용합니다. 특정 챗봇이나 AI, OCI 계정 없이 일반 편집기에서 이어서 작업할 수 있습니다.

## 시작하기

저장소 루트에서 Python 3.12 이상으로 실행합니다. 추가 패키지는 필요하지 않습니다.

```sh
python3 scripts/spec_init.py \
  --output specs/my-cost-summary \
  --title '비용 합산' \
  --purpose '사용자가 입력한 두 비용의 합계를 확인합니다.' \
  --requirement '두 정수 금액을 더한 값을 반환한다.' \
  --requirement '금액이 음수이면 입력 오류를 반환한다.'
```

`DRAFT`(초안)가 출력되고 새 폴더에 아래 네 파일이 생깁니다. 목적과 요구 문장은 그대로 보관합니다. 도구가 업무 규칙이나 합격 조건을 추측해서 추가하지 않습니다.

| 파일 | 작성할 내용 |
|---|---|
| `spec.md` | 요구별 입력·기대 결과·실패 조건을 구체화하고 검토합니다 |
| `design.md` | 요구를 어떻게 구현할지, 구성요소·데이터·권한·오류 처리를 정합니다 |
| `tasks.md` | 구현·검증 작업을 진행하며 실제 완료 항목만 체크합니다 |
| `traceability.json` | 요구 ID마다 실제 구현 파일과 테스트 이름을 연결합니다 |

제목·목적·각 요구는 한 줄이며 최대 2,000자입니다. `--requirement`를 반복해 최대 100개까지 입력합니다. 새 출력 폴더의 상위 폴더는 존재해야 하며, 저장소 밖 경로와 기존 출력 폴더는 거부합니다. 기존 명세에 요구를 추가하거나 요구 ID를 재배치하는 기능은 아닙니다.

## 제공 형태는 필요할 때만 적습니다

API, MCP 서버, 웹 GUI, CLI, 배치 작업 등은 가능한 예시입니다. 정해진 목록에서 고를 필요가 없으며, 아직 정하지 않아도 시작할 수 있습니다. 하나의 기능을 여러 방식으로 제공할 수도 있습니다.

기록하고 싶다면 생성 명령에 `--delivery 'API와 웹 화면을 함께 제공'`처럼 자유로운 설명을 추가하세요. `--delivery`는 여러 번 사용할 수 있습니다. 설명은 `spec.md`의 선택 메모에만 남습니다. 필수 요구·작업이나 별도 구현 틀을 자동 추가하지 않으며, 나중에 파일에서 직접 바꿀 수 있습니다.

필요한 경우 설계 과정에서 공통 업무 규칙과 각 입구의 입력·출력·권한을 구체화하시면 됩니다. 제공 형태 메모 자체는 검증 통과 조건이 아닙니다.

## 구현한 뒤 테스트 연결하기

예를 들어 `examples/my-cost-summary/cost.py`와 `test_cost.py`를 작성했다면 `traceability.json`의 해당 요구를 다음처럼 연결합니다. 경로는 **명세 폴더가 아닌 저장소 루트 기준**입니다.

```json
{
  "id": "REQ-001",
  "implementation": ["examples/my-cost-summary/cost.py"],
  "tests": [
    {
      "path": "examples/my-cost-summary/test_cost.py",
      "case": "CostTests.test_total"
    }
  ]
}
```

위 코드는 한 요구의 연결 예시입니다. 나머지 요구도 실제 구현·테스트와 연결해야 합니다. 테스트는 Python `unittest.TestCase` 기반이어야 하며, 예시 파일·클래스·메서드는 자동 생성되지 않습니다.

```sh
python3 scripts/check_spec_links.py specs/my-cost-summary
mkdir -p .run
python3 scripts/spec_evidence.py run specs/my-cost-summary --output .run/my-cost-evidence.json
python3 scripts/spec_evidence.py check .run/my-cost-evidence.json
```

초안 생성 직후에는 연결 목록이 비어 있으므로 첫 검사가 `Empty mapping`으로 실패하는 것이 정상입니다. 모든 연결을 채운 뒤에는 링크 검사를 통과할 수 있습니다. 링크 검사 통과는 요구 검토 완료나 실제 테스트 통과를 뜻하지 않습니다. 테스트를 실행한 뒤에도 요구를 충분히 검증하는지 사람이 확인해야 합니다.

## 기존 흐름과 연결하기

직접 작성한 요구로 시작해도 [테스트 결과 보관](../test-evidence/README.md)과 파일 변경 감지를 사용할 수 있습니다. 고객 인터뷰에서 출발한다면 [인터뷰 요구 초안](../interview-handoff/README.md)을 별도로 검토하고, [명시적 연결](../change-impact/README.md)로 해당 요구와 구현 명세를 연결합니다. ID가 같다는 이유로 같은 요구라고 자동 판단하지 않습니다.

이 기능은 명세 작성을 시작하는 도구입니다. 검토 기록, 코드, 통과 테스트, 배포 결과를 자동 생성하지 않습니다. 완성된 흐름을 먼저 보고 싶다면 [합성 자료 전체 체험](../sdd-walkthrough/README.md)을 이용하세요.
