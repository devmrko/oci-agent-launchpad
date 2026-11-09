# 에이전트 Hello World

**최종 목표는 Companion 빌드 → OCI 배포 → 실제 모델·도구 실행 → Langfuse 관측입니다. 현재 예제는 그 선행 구현이며 배포 완주는 아직 미완료입니다.** [완주 조건과 현재 공백](DELIVERY.md)을 기준으로 진행합니다.

“지금 서울 몇 시인가요?”라는 질문으로 에이전트의 최소 동작을 확인합니다.

**질문 → 모델이 도구와 인자를 선택 → 앱이 허용 여부 검사 → 시간 도구 실행 → 결과 표시**

시간을 모델이 지어내지 않고 실행 환경의 시계에서 가져옵니다. 서울·도쿄·런던만 허용하며 업무 데이터나 외부 시스템을 변경하지 않습니다. 서버 시계가 정확하다는 전제가 필요합니다.

## 바로 실행

저장소 루트에서 Python 3.12 이상으로 실행합니다. 기존 `.venv`를 사용할 수 있습니다.

```bash
.venv/bin/python examples/hello-agent/agent.py --mode demo '지금 서울 몇 시인가요?'
.venv/bin/python examples/hello-agent/agent.py --mode demo '안녕하세요'
```

`demo`는 연결 없이 흐름을 배우는 규칙 기반 시연입니다. 실제 LLM을 호출하지 않으며 결과에 `mode: demo`, `model_used: false`를 표시합니다. 현재 시각은 실행할 때마다 달라집니다. `decision`, `tool_result`, `answer`를 순서대로 읽으면 됩니다.

## 실제 OCI 모델 사용

기본 모드는 `oci`입니다. 이 저장소의 기존 OCI SDK 버전은 `oci==2.188.0`이며 SDK가 있는 환경을 사용합니다. 로컬은 config 인증, VM은 HELLO_OCI_AUTH=instance, OKE는 HELLO_OCI_AUTH=oke를 선택하며 필요한 모델 호출 권한이 있어야 합니다. 키를 코드나 Git에 넣지 않습니다.

다음 값은 실제 사용 가능한 값으로 설정해야 합니다. 모델 처리가 허용되는 리전을 명시합니다.

```bash
export HELLO_OCI_REGION='<모델 지원 및 데이터 처리 허용 리전>'
export HELLO_OCI_COMPARTMENT='<호출 대상 compartment OCID>'
export HELLO_OCI_MODEL='<GenericChatRequest 호환 모델 ID>'
export HELLO_OCI_PROFILE='DEFAULT'
.venv/bin/python examples/hello-agent/agent.py '지금 서울 몇 시인가요?'
```

모델은 JSON으로 동작을 선택합니다. SDK의 native function-calling 대신 작은 JSON 계획을 사용한 예제입니다. 허용된 스키마와 도구만 실행하고 잘못된 응답·모델 장애는 실패로 끝냅니다. 데모로 자동 전환하지 않습니다. 답변은 도구 결과로 템플릿 생성하므로 두 번째 모델 호출이 없습니다. 이 예제는 자율 반복·다중 도구 계획을 구현하지 않습니다.

## 고객 요구와 합격 기준

| 질문 | 예제 답변 | 합격 기준 |
|---|---|---|
| 무엇을 도와주는가 | 인사와 세 도시의 현재 시간 안내 | 선택 도시·시간대·실측 시각 표시 |
| 어떤 행동이 가능한가 | 읽기 전용 시간 조회 | 임의 명령·파일·네트워크 도구 실행 불가 |
| 모르는 요청은 | 지원 범위 안내 | 미지원 도시·업무를 지어내지 않음 |
| 무엇을 기억하는가 | 아무것도 영속 저장하지 않음 | DB·세션·장기 기억 없음 |
| 실패하면 | 명시적 오류와 비정상 종료 | 실제 모델 실패를 성공/데모로 숨기지 않음 |

## 구성과 범위

| 기능 | 이 예제 | 확장할 때 |
|---|---|---|
| Runtime | 로컬 CLI | 독립 API·컨테이너 → VM/OKE |
| 모델 | OCI SDK 명시 호출 / 데모 분리 | Foundation 공통 모델 어댑터 선택 검토 |
| 도구·정책 | allowlist·엄격한 인자 검사 | Gateway·Identity·업무 승인 |
| 관측 | 콘솔의 선택·도구 결과·답변 | 동일 단계에 Langfuse trace 연결 |
| Memory | 불필요하므로 없음 | 기억할 업무 요구가 생기면 Oracle Agent Memory |
| Companion | 아직 등록·배포하지 않음 | 앱 API·health 계약을 갖춘 뒤 등록 |

Service Desk의 DB·웹 인증·메모리 코드를 의존하지 않는 교육용 단일 파일입니다. Python Foundation 통합, 웹 GUI, OCI 배포, Langfuse, 운영 인증은 이 예제에 아직 구현하지 않았습니다. 전체 플랫폼 기능 완료를 뜻하지 않습니다.

## 검증

```bash
cd examples/hello-agent
../../.venv/bin/python -m unittest -v test_agent
```

로컬 데모와 경계 검증을 위한 테스트입니다. 실제 OCI 모델 검증과 분리합니다. OCI 모델·리전·compartment를 지정한 실제 호출 성공이 확인되기 전에는 OCI 검증 완료라고 표시하지 않습니다.

더 보기: [기능 개요](../../docs/platform-overview.md), [Service Desk 전체 예제](../service-desk/README.md).
