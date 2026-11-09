# 변경 사례: 숙박 상한을 14박으로 확대

사용자가 11~14박 출장의 숙박비도 웹과 CLI에서 계산할 수 있도록 기존 앱을 확장합니다. 실제 고객 요청이 아닌 합성 학습 시나리오입니다.

## 구현 전 합격 조건

- 기존 1·2·10박 결과를 유지합니다.
- 11박은 1,100,000원, 14박은 1,400,000원입니다.
- 15박·0박·음수·소수·불리언은 거부합니다. CLI의 문자열 인자는 정수 변환 후 검사합니다.
- 웹 선택지에는 1~14박이 있고 15박은 없습니다. 규정 계산 API와 CLI는 같은 결과를 냅니다.
- OCI 호출 한도 10회와 접근 제어는 유지합니다. 일반 계산에는 모델 호출이 없습니다.

## 변경 경계와 구현 계획

REQ-001과 REQ-006의 허용 범위를 갱신합니다. 공통 계산 함수, CLI 도움말, HTTP 입력 오류 안내, 웹 선택지를 함께 바꿉니다. 기존 테스트의 11박 거부 조건은 15박 거부로 바꾸고 11박·14박 허용 검증을 추가합니다. 화면은 제공 HTML의 선택지까지 자동 검증하고 시각적 배치는 별도 범위로 남깁니다.

합성 인터뷰의 기존 revision 1은 보존하고, 수정 답변을 supersedes로 연결한 revision 2 예제를 추가합니다. 전체 체험은 새 요구에서 시작하며 후속 미구현 변경(21박)을 감지합니다. 사람이 실제로 승인했다는 기록은 만들지 않습니다.

## 따라 확인하기

```sh
python3 -S examples/enterprise-ai-web/cli.py 14
python3 -S examples/enterprise-ai-web/cli.py 15
python3 -S -m unittest discover -s examples/enterprise-ai-web -p 'test_*.py'
```

첫 명령은 amount=1400000의 JSON과 종료 코드 0을 반환해야 합니다. 두 번째 명령은 오류와 종료 코드 2를 반환해야 합니다. 웹에서는 `python3 examples/enterprise-ai-web/server.py --offline` 실행 후 14박을 선택합니다.

이 문서와 연결 명세·테스트를 함께 읽으면 요구가 구현 파일과 실행 결과로 이어지는 범위를 확인할 수 있습니다. 배포·실제 OCI 14박 호출·고객 인수 검증은 포함하지 않습니다.

## 확인한 결과

2026-11-09: 새 합격 조건을 기존 10박 구현에 실행했을 때 11·14박 함수/CLI/API 검증에서 실패했습니다. 구현 수정 후 앱 테스트 16건과 SDD 도구 테스트 44건이 통과했습니다. CLI 14박의 실제 출력 amount=1400000을 확인했습니다. HTTP 테스트는 제공 HTML의 선택지 1~14와 15박 거부, OCI 미호출·한도 유지까지 검사합니다. 화면 클릭·시각 배치와 실제 OCI 호출은 이번 검증에 포함하지 않았습니다.

연결된 테스트: EstimateTests.test_rule_amounts, EstimateTests.test_invalid_nights, BoundaryTests.test_extended_nights_api_and_page, CliTests.test_json_matches_shared_rule, CliTests.test_invalid_input_has_no_success_output. 이 이름은 traceability.json을 통해 실제 파일에 연결됩니다.
