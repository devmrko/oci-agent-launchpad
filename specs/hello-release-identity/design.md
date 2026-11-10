# 설계와 검증 범위

Hello Agent 전용 hello_release 모듈이 JSON 정규화 해시, 허용 필드와 설치 파일 검사를 담당합니다. 기존 앱/배포에 선택적으로 추가하며 다른 앱에 특정 명세 형식이나 개발 도구를 강제하지 않습니다.

빌드 준비 도구는 command_evidence의 파일 스냅샷을 재검사하고 이 명세, Hello Agent 업무 명세, 테스트, 네 개 실행 모듈과 pyproject.toml의 포함을 검사합니다. 식별 정보에는 release_id, 앱 버전, 업무 명세 SHA, 실행 소스 묶음 SHA, 테스트 근거 SHA와 실행 파일별 SHA를 넣습니다. spec_sha256은 specs/hello-agent/spec.md의 해시이며 릴리스 기능 명세와 구분합니다. release_id는 자기 자신을 제외한 본문을 정규화한 SHA-256입니다. 서명이나 이미지 검증을 대신하지 않습니다.

앱은 HELLO_RELEASE_IDENTITY 환경 변수의 JSON을 읽고 네 모듈의 실제 설치 파일과 비교합니다. 잘못된 설정은 시작 실패이며 예외에 비밀값이나 본문을 넣지 않습니다. health와 채팅 응답에는 해시 요약만 넣습니다. OTLP의 모든 observation metadata에 같은 요약을 넣습니다. 호출자의 메시지나 요청 필드로 식별 정보를 지정할 수 없습니다.

완료 기준은 생성 도구의 stale 거부와 실제 생성물 로딩, 소스 변조 시 시작 실패, 인증된 API 응답→OTLP payload 배선 검사, OKE env/annotation 배선 검사입니다. 모델과 OTLP는 로컬 대역을 쓰고 외부 서비스 호출은 없습니다. 기존 OCI 0.1.0 실행의 명세 연결 상태는 바꾸지 않습니다.
