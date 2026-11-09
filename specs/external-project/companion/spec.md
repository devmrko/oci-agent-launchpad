# OCI Companion 컨테이너 예제의 HTTP 응답

공개 저장소의 기존 앱을 Launchpad 밖에서 검증하기 위한 합성 명세입니다.

## REQ-001 기존 상태 응답 유지

payload는 service=oci-companion-container-demo, status=ok를 반환합니다.
기존 test_app.py의 두 테스트를 유지합니다.

## REQ-002 HTTP 상태 확인

GET /는 JSON 상태 응답을 200으로 반환합니다. 실제 로컬 HTTP 요청으로 검사합니다.
