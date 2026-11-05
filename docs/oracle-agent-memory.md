# 새 ADB에 사용자별 기억 저장하기

서비스 데스크 0.4.0은 사용자가 명시적으로 보낸 기억을 Oracle Agent Memory에 저장하고 의미로 검색합니다. 대화 전체를 자동 저장하지 않으며, 접수·승인·언어 설정은 기존 SQLite에 남습니다. 기억 검색 결과는 업무 규정이나 실행 권한으로 취급하지 않습니다. 별도 기억 API와 명시적인 채팅 명령을 지원합니다. 일반 질문의 답변에 기억을 자동 주입하는 기능은 아직 없습니다.

## 구성

- 서울 `Joungmin.Ko`: 전용 `oci-agent-launchpad-memory` / `LPMEMORY`, Oracle AI Database 26ai, 2 ECPU·20GB, 자동 확장 끔. 유료 리소스입니다.
- 예제 VM: TLS로 ADB 접속. ADB IP 허용 목록은 이 VM만 포함합니다.
- 설치 계정 `LP_MEMORY_OWNER`와 실행 계정 `LP_MEMORY_APP` 분리. 실행 중에는 기존 `LPMEM` 스키마만 사용합니다.
- Python Foundation 0.1.2: 인증 주체와 앱 namespace에서 사용자 범위를 계산하고 SDK 검색 조건과 결과를 모두 검사합니다.
- SDK: `oracleagentmemory==26.8.0`, `oci==2.188.0`. OCI 2.180.0과는 cryptography 제약이, 2.190.0과는 urllib3 제약이 충돌하여 함께 설치 가능한 버전을 고정했습니다.
- 임베딩: VM Instance Principal → Ashburn `cohere.embed-v4.0`, 1536차원. 현재 합성 데이터만 검증했습니다. 실제 고객 데이터의 국외 처리는 별도 결정이 필요합니다.

## 채팅에서 사용

같은 사용자의 서로 다른 세션에서도 다음 명령으로 기억을 저장·조회합니다. `/api/chat`의 `message`에 넣습니다.

- `기억해 주세요: VPN 안내는 짧은 한국어 설명을 선호합니다.`
- `기억에서 찾아 주세요: VPN 설명 선호`
- 영어 명령: `remember: ...`, `recall: ...`

콜론 뒤 내용만 저장하거나 검색합니다. 명시적 저장 요청이 없는 일반 채팅은 기억에 저장하지 않습니다. 조회 답변에는 기억 출처 ID와 원문이 표시됩니다. 기억에 승인·도구 실행 지시가 들어 있어도 실행하지 않습니다. 자동 요약·선호 추출·일반 답변 개인화와는 구분됩니다.

0.4.0 검증: 자동 테스트 14개 통과. 실제 ADB에 채팅으로 저장하고 새 세션에서 동일 ID를 회상했으며, 접수 미발생·추적 원문 제외를 확인했습니다. Companion에서도 `explicit-memory` 실행과 앱 UP을 확인했습니다.

## API 사용

기존 서비스 데스크 인증 토큰을 사용합니다. 토큰을 문서·스크린샷·Git에 넣지 않습니다. 앱 프로세스에는 `DESK_MEMORY_CONFIG`로 보호된 JSON 설정 파일 경로를 지정합니다. 필수 키는 `user`, `password`, `dsn`, `compartment`입니다. `dsn`은 ADB가 제공하는 TLS 연결 문자열을 그대로 사용합니다.

```http
POST /api/memories
Authorization: Bearer <existing-demo-token>
Content-Type: application/json

{"text":"[합성 예제] VPN 문제는 한국어로 간결하게 설명받고 싶습니다."}
```

```http
POST /api/memories/search
Authorization: Bearer <existing-demo-token>
Content-Type: application/json

{"query":"VPN 설명 언어 선호", "limit":5}
```

응답은 `backend: oracle-agent-memory`와 기억 ID·본문 목록을 반환합니다. 사용자가 별도 `user_id`를 전달할 수 없습니다. 저장 결과가 불확실하면 자동 재시도하지 않고 조회부터 하도록 오류를 반환합니다. 동일 문장을 여러 번 명시적으로 저장하면 별도 기억으로 남습니다.

## 배포·검증

`deploy/provision_memory.py`는 새 ADB를 한 번 생성하고 로컬 상태 파일에 ID를 기록합니다. `deploy/initialize_memory.py`는 VM에서 관리자 정보를 표준 입력으로 받아 전용 계정·스키마와 실행 권한을 준비합니다. 비밀값은 출력하지 않습니다. `deploy/install_memory.sh`는 별도 실행 환경으로 배포하고 health 실패 시 이전 서비스 설정으로 복구합니다.

`examples/service-desk/scripts/smoke_oracle_memory.py`는 실제 ADB 저장·의미 검색·재연결 후 지속성·다른 사용자 결과 차단을 확인합니다. `smoke_memory_api.py save` 후 서비스를 재시작하고 `smoke_memory_api.py verify`를 실행하면 HTTP 경로의 지속성과 원문 없는 추적을 확인할 수 있습니다. VM 내 보호된 예제 계정 파일을 사용하는 검증용 스크립트입니다.

Companion `/agents`에는 `memory-save`, `memory-search`의 성공·실패와 지연 시간이 표시됩니다. 기억 원문은 표시하지 않습니다. 사용자 격리는 현재 애플리케이션 계층에서 검증하며 DB 수준의 Deep Data Security를 구성했다는 의미는 아닙니다.

참고: [Oracle Agent Memory ADB 연결](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/run-adb.html), [OCI 임베딩 호출 권한](https://docs.oracle.com/en-us/iaas/Content/generative-ai/embedding-permissions.htm).

실제 검증 완료(2026-11-06): SDK 직접 저장·검색·재연결·사용자 격리 PASS, HTTP 저장 후 systemd 재시작·검색·추적 원문 제외 PASS. Companion 화면에서 앱 0.3.0 UP과 memory-save/memory-search 성공 기록을 확인했습니다. 단일 실행의 지연은 각각 약 1.02초·0.94초였으며 성능 보장 수치가 아닙니다.
