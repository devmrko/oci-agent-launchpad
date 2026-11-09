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
