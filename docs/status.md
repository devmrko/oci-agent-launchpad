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
