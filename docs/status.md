# 현재 상태 — Companion 배포·복구 연결

2026-11-06: Companion의 배포 화면에서 서울 예제 VM의 OCI DevOps 파이프라인을 실행했습니다. 0.4.0 → 0.3.0 복구는 OCI `SUCCEEDED`와 Companion의 `UP · 0.3.0`을 확인했고, 화면에서 시작한 0.4.0 재배포도 OCI API `SUCCEEDED`와 실제 VM health `UP · 0.4.0`을 확인했습니다. 최종 브라우저 재확인은 Edge의 다른 확장 UI가 자동화를 차단하여 진행하지 못했습니다.

서비스명·릴리스 루트·포트·기대 버전·상태 확인 제한 시간은 환경별 JSON으로 지정합니다. 릴리스 전환 실패 시 직전 systemd 설정과 앱 버전을 복구하며, ADB 메모리와 SQLite 데이터는 변경하지 않습니다. 자동 실패 복구는 로컬 실패 주입 테스트, 버전 왕복 전환은 실제 VM과 DevOps로 검증했습니다.

Companion 기능 브랜치 `feature/agent-operations`의 `3c91a66` 기준 전체 테스트 108개, Launchpad 배포 테스트 14개 및 하위 검사 3개가 통과했습니다. 최종 Companion 빌드는 로컬 8091 포트에서 실행 중입니다. [배포·복구 사용법과 변수](../deploy/RELEASES.md)를 참고하세요.

현재 완료 범위는 **이미 설치된 릴리스의 활성화·복구**입니다. 패키지의 Artifact Registry 전송·검증·설치와 Terraform 기반 전체 DevOps/IAM/VM 초기화는 남아 있습니다. AgentCore 주요 기능 전체의 대체가 완료된 것은 아닙니다.

아래는 이전 버전 검증 이력입니다.

---

# 채팅 기억 연결 — 0.4.0

2026-11-06: 채팅에서 명시적으로 요청한 기억을 Oracle Agent Memory에 저장하고 다른 세션에서 조회하는 흐름을 실제 OCI에서 검증했습니다. 자동 테스트 14개 통과, Companion 화면 UP·기억 도구 성공 확인. 사용법은 [Oracle 기억 가이드](oracle-agent-memory.md)를 참고하세요. 일반 질문에 대한 자동 기억 추출·답변 개인화는 아직 없습니다.

아래는 이전 버전의 검증 이력입니다.

---

# 현재 상태 — Oracle Agent Memory 연결

2026-11-06: 서울 Joungmin.Ko에 새 ADB `oci-agent-launchpad-memory`를 생성하고 서비스 데스크 0.3.0에 Oracle Agent Memory 26.8.0을 연결했습니다. 실제 저장·의미 검색·사용자 격리·앱 재시작 후 복원·원문 없는 실행 추적을 검증했습니다. Foundation 38개, 예제 13개 테스트와 현재 wheel 설치 검증을 통과했습니다.

[Oracle 메모리 구성·사용 방법](oracle-agent-memory.md)을 참고하세요. 기억은 별도 API로 명시적으로 저장·검색하며, 채팅 자동 주입·자동 추출은 미구현입니다. 아래 0.2.0 표는 이전 검증 기준입니다. 전체 AgentCore 대체 플랫폼과 Companion 배포 실행은 여전히 완료되지 않았습니다.

---

# OCI에서 에이전트를 실행하고 Companion으로 확인하기

고객 유스케이스를 AI-DLC 템플릿으로 구체화하고, Python Foundation의 공통 실행 기능을 사용하는 에이전트를 OCI에 배포하는 프로젝트입니다. 현재 서비스 데스크 예제로 실제 모델 호출과 승인 흐름을 확인할 수 있습니다. AgentCore 주요 기능을 대체하는 전체 플랫폼은 아직 완성되지 않았습니다.

## 지금 확인하는 방법

로컬 OCI Companion `http://127.0.0.1:8091/agents`에서 DEFAULT 프로파일로 연결하고 `ap-seoul-1 / Joungmin.Ko`를 선택합니다. SSH 터널과 Companion 프로세스가 실행 중이어야 합니다. 에이전트 실행 화면에서 앱 0.2.0, 모델·리전, 토큰 수, 지연 시간, 도구 실행 결과를 확인합니다. 조회 대상은 설정된 합성 예제 계정입니다.

## 2026-11-05 검증 결과

| 기능 | 확인한 범위 | 남은 범위 |
|---|---|---|
| Runtime | 서울 신규 Oracle Linux VM, systemd 실행·재시작, health 0.2.0 | 작업별 격리, 자동 확장, 고가용성 |
| 모델 | VM Instance Principal로 OCI Generative AI 호출, 실제 예제 전체 흐름 통과 | 서울 모델 호출 실패 해소, 다단계 에이전트 루프 |
| Gateway | Foundation 0.1.1의 도구 등록·엄격한 입력 검증·실행 예산 | 네트워크 MCP Gateway, 외부 커넥터 |
| Identity / Policy | 예제 계정 인증, 세션 소유권, 쓰기 권한, 사람 승인, 중복 접수 방지 | 운영 IdP 통합 검증, 중앙 정책 관리 |
| Memory | SQLite 세션·업무 상태 지속성 | 의미 기반 장기 메모리, 공유 메모리 정책 |
| Observability | 요청·모델·토큰·도구 기록, Companion 실제 화면 확인 | OCI APM 통합, 알림, 전체 사용자 관측 |
| Evaluations | 앱 자동 테스트 12개, 실제 모델 smoke 통과 | 품질 평가 데이터셋, 회귀 평가 파이프라인 |
| Code Interpreter / Browser | 미구현 | 격리 실행·브라우저·네트워크 통제 |
| 배포 | 소스 커밋을 고정한 SSH 배포, DevOps 환경 등록 | Companion에서 OCI DevOps 배포 실행·실패 복구 검증 |

앱 코드는 `2669f0d`, Foundation은 `c98f69dd20c005ac5aa244dd03f110ddeed368dd` 기준입니다. Foundation 36개 테스트와 wheel 설치 검증, 앱 12개 테스트, Companion 103개 테스트가 통과했습니다. 실제 OCI smoke는 규정 출처, 승인 전 접수 차단, 중복 승인 방지, 요청 추적을 검증했습니다. Companion 화면에서도 실제 모델의 search/propose와 approve 기록을 확인했습니다.

VM과 SQLite 데이터는 서울에 있습니다. 모델은 서울 API 호출에서 공급자 모델 접근 오류가 발생해 Ashburn의 Gemini 2.5 Flash Lite를 사용했습니다. 전송한 입력은 합성 데모 데이터이며, 실제 고객 데이터의 해외 처리를 승인받았다는 의미가 아닙니다. 모델은 search/propose 선택에 사용하며 응답 본문은 예제 정책 데이터로 구성합니다.

## 다음 완료 조건

1. Companion에서 선택한 서울 구획의 OCI DevOps 파이프라인을 실행하고 배포 ID·완료 상태·health 버전을 연결한다.
2. 모델 오류·도구 거부·시간 초과를 재현하고 화면에 원인 단계가 표시되는지 확인한다.
3. 장기 메모리와 평가를 추가한 뒤 Code Interpreter·Browser 격리 실행을 구현한다.

상세 설계는 [플랫폼 계획](oci-agent-platform-plan.md), [Companion 통합 계획](companion-integration-plan.md), [서비스 데스크 예제](../examples/service-desk/README.md)를 참고합니다.
