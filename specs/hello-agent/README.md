# 두 번째 기존 앱에 SDD 적용하기

**Hello Agent에 지원 도시 목록 조회를 추가하면서, 기존 앱의 요구·코드·테스트와 개발자 작업 전달 도구를 연결했습니다.** 출장비 예제에만 종속된 흐름인지 확인하기 위한 두 번째 적용 사례입니다. 개발자는 계정 없이 도구 선택·검증·실행 결과를 확인할 수 있습니다.

## 실행해 보기

Python 3.12 이상에서 저장소 루트로 이동해 실행합니다. 추가 패키지와 OCI 계정이 필요하지 않습니다.

```sh
python3 -S examples/hello-agent/agent.py --mode demo '도시 목록'
python3 -S -m unittest discover -s examples/hello-agent -p test_agent.py
```

첫 명령은 `list_cities`, `model_used: false`와 서울/Asia/Seoul, 도쿄/Asia/Tokyo, 런던/Europe/London을 포함한 JSON을 반환합니다. “지원 도시”, “어떤 도시를 지원하나요?”도 데모에서 처리합니다. 데모는 정해진 표현을 인식하는 규칙 기반 경로이며 자연어 전반을 이해하는 모델이 아닙니다.

## 실제로 진행한 변경

1. 기존 시간 조회·도구 검증·데모 입력 동작을 요구 3개에 연결하고 기존 테스트 6개를 확인했습니다.
2. 변경 전에 REQ-002·REQ-003에 대해 도시 목록 조회 요청과 합격 조건을 담은 작업 지시서를 생성했습니다.
3. 도시 목록 테스트를 먼저 추가했습니다. 기존 구현이 unsupported로 답해 실패하는 것을 확인했습니다.
4. 현재 Codex가 agent.py의 도구 허용 목록·데모 선택·실행 결과와 설명 프롬프트를 수정했습니다. 임의 명령과 추가 인자 거부를 유지했습니다.
5. REQ-004와 테스트 연결을 추가한 뒤 실제 테스트 8개를 실행했습니다. 반환 보고서에는 변경된 5개 파일, 현재 파일에 맞는 PASS 근거, 사람 검토 대기인 합격 조건이 함께 표시됐습니다.

다른 개발자나 외부 AI 도구를 자동 호출한 사례는 아닙니다. 같은 세션의 Codex가 작업 지시서를 참고해 구현했으며, 실제 고객 승인·독립 개발자 인수·OCI 호출·웹 통합·배포 검증은 수행하지 않았습니다. 기존 배포 기록은 이 변경의 검증 결과로 재사용하지 않습니다.

## 다음 변경 작업에 사용하기

구현을 시작하기 전에 원하는 요구와 합격 조건으로 새 작업 지시서를 만듭니다. 아래는 현재 기능의 유지·검토를 위한 예시이며 추가 구현을 자동 수행하지 않습니다.

```sh
mkdir -p .run
python3 scripts/developer_handoff.py prepare specs/hello-agent \
  --requirement REQ-002 --requirement REQ-004 \
  --request '지원 도시 목록 기능을 검토하고 필요한 수정 사항을 반영해 주세요.' \
  --acceptance '도시와 시간대가 요구 명세와 일치하고 추가 인자는 거부된다.' \
  --acceptance '기존 시간 조회와 인사 및 demo의 model_used=false를 유지한다.' \
  --output .run/hello-task
```

선택한 개발 도구나 사람이 `TASK.md`와 관련 코드를 보고 작업한 뒤 검증합니다.

```sh
python3 scripts/spec_evidence.py run specs/hello-agent --output .run/hello-evidence.json
python3 scripts/developer_handoff.py report .run/hello-task/baseline.json \
  --evidence .run/hello-evidence.json --output .run/hello-review
```

기존 결과는 덮어쓰지 않습니다. 재실행 시 새 출력 이름을 사용하세요. `TESTS_CURRENT_REVIEW_PENDING`은 테스트 기록이 현재 코드와 일치한다는 뜻이며, 요구 충족 여부는 diff와 테스트를 보고 검토해야 합니다.

[요구 명세](spec.md) · [설계와 변경 범위](design.md) · [작업 기록](tasks.md) · [구현·테스트 연결](traceability.json)
