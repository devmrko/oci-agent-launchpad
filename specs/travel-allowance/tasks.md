# 구현과 검증 작업

- [x] TASK-001: REQ-001 순수 규정 계산 함수와 입력 경계 시험
- [x] TASK-002: REQ-002 오프라인 시작·계산 API·OCI 경로 차단
- [x] TASK-003: REQ-003 화면에서 규정 계산과 AI 설명 선택 분리
- [x] TASK-004: REQ-004·REQ-005 결과 판정·접근·한도 회귀 시험
- [x] TASK-005: 요구 ID와 코드·테스트 링크 검사, 계정 없는 실행 재현

완료 표시에는 검증 명령과 범위를 남깁니다. OCI 앱 배포나 사람의 화면 검토는 수행 전까지 완료로 표시하지 않습니다.

## 검증 기록

2026-11-09: 앱 테스트 12건, 명세 링크 검사기 테스트 4건 통과. Python의 `-S` 옵션으로 외부 패키지를 로드하지 않은 상태에서 HTTP 규정 계산과 OCI 요청 차단을 확인했습니다. TASK-003은 화면 코드와 HTTP 응답 구현 완료이며 브라우저 시각 검증은 미완료입니다.

명령: `python3 scripts/check_spec_links.py specs/travel-allowance`, `python3 -m unittest discover -s examples/enterprise-ai-web -p "test_*.py"`, `python3 -m unittest discover -s scripts -p "test_check_spec_links.py"`.

## CLI 확장 검증

- [x] REQ-006: 계산 함수를 allowance.py로 분리하고 CLI와 웹에서 재사용
- [x] REQ-006: CLI JSON 결과와 잘못된 입력의 종료 코드·출력 검증
- [x] 공통 파일과 CLI 테스트를 traceability.json에 연결

2026-11-09: 앱 테스트 14건 및 SDD 도구 테스트 44건 통과. 도구 테스트에는 복사한 작업 폴더에서 전체 SDD 체험을 실행하는 검증이 포함됩니다. CLI 정상 입력 1·2·10박과 범위 밖·소수·문자·누락·초과 인자를 실제 하위 프로세스로 확인했습니다. 이번 변경에서 실제 OCI 호출·배포·브라우저 시각 검증은 수행하지 않았습니다.

## 14박 변경 완료 범위

- [x] REQ-001·REQ-006: 11·14박 허용과 15박 거부 합격 조건 작성 및 기존 구현의 실패 확인
- [x] 공통 계산·CLI·HTTP 안내·웹 선택지 수정
- [x] 기존 입력·접근 제어·OCI 한도 회귀 확인
- [x] 합성 인터뷰 수정 이력과 전체 체험 예제 갱신

2026-11-09: 앱 테스트 16건 및 SDD 도구 테스트 44건 통과. [변경 요청에서 실행 결과까지](change-14-nights.md)에 검증 범위를 기록했습니다.
