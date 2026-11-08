# 독립 에이전트 플랫폼: 완료 범위와 재현 배포 점검

2026-11-09. OCI 엔지니어가 현재 쓸 수 있는 기능과 다음 구현 순서를 판단하기 위한 코드·검증 기록 대조다. 단일 개발 환경의 성공을 전체 AgentCore 동등성이나 운영 준비 완료로 확대하지 않는다.

## 현재 쓸 수 있는 범위

| 기능 | 현재 상태와 근거 | 다음 완료 조건 |
|---|---|---|
| Runtime | VM와 OKE에서 Service Desk 실행 검증. OKE 0.6.0, 단일 Pod/PVC | 동시 실행·작업 취소·세션 격리·다중 replica 검증 |
| Memory | Oracle Agent Memory/ADB 저장·새 세션 검색. OKE runtime-check PASS | 운영 인증, 다중 사용자/에이전트 경계 재시험·복구 |
| Identity | 합성 토큰 접근 및 OCI workload identity 모델 호출 검증 | Identity Domains/OIDC, 외부 사용자 위임·회수 |
| Gateway | 앱의 제한된 도구 호출은 존재. 중앙 MCP Gateway 검증은 없음 | OCI API Gateway 진입 + 필요 시 ContextForge 카탈로그/중계 시험 |
| Policy | 예제의 소유권·승인·중복 방지 | 중앙 정책 연결, OPA 적용 시 장애 시 거부·인자 변조 통합 시험 |
| Observability | OKE 요청 3건·관측 7건, 모델 입출력·메모리 본문 제외 검증 | 다중 에이전트·관측 중단·유실·상시 알람 |
| Evaluations | 앱 capabilities에 not_implemented | Langfuse 데이터셋 기반 업무·보안 합격 기준 및 실행 결과 |
| Code Interpreter / Browser | 앱 capabilities에 not_implemented | OCI 우선 격리 실행, 부족한 브라우저는 OSS 연결; 취소/정리/망 경계 시험 |
| 빌드·배포 | Functions 빌드 경로와 OCI DevOps OKE 배포 성공 기록 존재 | 새 고객 환경에서 한 입력으로 준비→새 소스 빌드→배포 완주 |
| Companion | 독립 등록 앱, OCI 의존 리소스, Deployment/Pod/노드 조회. 0adfb5f, 156개 테스트 통과 | 상시 사설 연결, OCI 알람/로그 연결, 설정 가져오기 |
| 독립성 | 실행 서비스와 Companion은 별도 프로세스/저장소 | IND-01의 의도적인 Companion 중지 중 업무·메모리·관측 연속 시험 |
| 복구·HA | OKE Pod 재생성 후 동일 PVC의 요청 3건 보존 | 다중 노드·DB/큐 복구·RPO/RTO 측정. 재시작 보존은 백업 복구가 아님 |

근거: `examples/service-desk/service_desk/app.py`, [OKE 배포 실측](../../infra/terraform/oke-delivery/README.md), [빌드](../../deploy/BUILD.md), [관측](../../deploy/SERVICE-DESK-LANGFUSE.md), Companion `docs/design/oke-operations.md`. 로컬 비공개 증거의 `oke-runtime-check.json`, `oke-observations-check.json`, `oke-persistence-check.json`은 PASS이며 `oke-deployment-run.json`은 SUCCEEDED다. 이번 점검은 그 기록과 소스를 대조했고 모든 클라우드 시험을 다시 실행한 것은 아니다.

기존 로컬 검증표 `docs/design/agent-platform-acceptance.md`는 신규 OCI+OSS 조합의 완료 조건이다. OPA/ContextForge를 실제 설치하지 않은 상태에서 기존 앱 승인·도구 시험으로 GW/POL 항목을 통과 처리하지 않는다. REL/OBS/MEM에는 OKE의 부분 증거가 생겼지만 각 항목의 전체 부정 조건을 모두 재검증한 것은 아니다.

## 비교 기준의 추가 기능

2026-11-09 조회한 [AWS 공식 개요](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)에는 기존 주요 기능 외에 Harness, Payments, Optimization, Registry도 나열된다. 현재 저장소의 동등 기능으로 표시하지 않는다. 이들은 추적 대상으로 기록하며 기존 합의한 뼈대 완료 범위를 자동 확대하지 않는다. OCI 지원 여부와 대체 제품 선택은 기능별 별도 확인 대상이다.

## 재현 배포에서 확인된 빈틈

1. 기존 환경 렌더러는 `agent-monitor.json` 단일 앱 형식을 만든다. Companion의 다중 앱 레지스트리·의존 참조·OKE 조회 설정을 생성하지 않는다.
2. OKE, 메모리, 관측, 배포 파이프라인 변수 파일은 나뉘어 있다. 한 입력으로 모든 OCI 자원·Vault·ADB 초기화·IAM·빌드를 안전하게 적용하는 통합 경로는 미완료다.
3. 현재 OKE 관리와 앱 health는 Mac의 SSH 터널/port-forward를 사용한다. 고객 운영용 상시 연결 완료가 아니다.
4. 실제 pull 인증은 운영자 토큰이고, ADB 접근에는 노드 IP 반영이 필요하다. 전용 인증·회전·노드 교체 대응을 완료해야 한다.

## 이번 구현: 다중 앱 연결 설정 생성기

새 생성기는 scope + apps 입력에서 `agent-connections.json`, `agent-credentials.json`, `oke-workloads.json`을 새 폴더에 만든다. VM/OKE, 의존 리소스, kubeconfig·토큰 파일 참조를 변수화한다. 비밀값을 받거나 읽지 않고 OCI 변경·명령 실행·기존 레지스트리 덮어쓰기를 하지 않는다. 안정적인 앱 key와 scope에서 ID를 생성해 재생성 시 같은 앱으로 연결한다. 기존 앱 ID를 유지할 때는 명시적으로 지정한다.

형식 검증은 접근 권한·대상 구획·kubeconfig 주체를 검증한 것이 아니다. Companion은 조회 시 기존 scope/OCI 검사를 계속 수행한다. 결과는 독립 Companion 인스턴스의 시작 설정으로 지정해 사용한다. 실행 중인 레지스트리에 자동 병합하는 기능은 후속이며 기존 파일 위에 복사하지 않는다. 완료 기준: 두 앱 설정 생성, 기존 Companion JSON 계약 호환, 미정값·잘못된 유형/주소/중복 참조 차단, 새 폴더 전용 출력·비밀 미조회 테스트.

## 이어서 수행할 순서

연결 설정 생성 → Companion 독립성 시험 → OCI Monitoring/Logging 연결 → 빈 환경 배포 통합 및 선행 권한 검사 → 운영 Identity/Gateway/Policy → 평가와 격리 도구. 새 기능 구현마다 실제 시험 증거와 미검증 범위를 갱신한다.

## 이번 설정 생성기 검증 결과

관련 Python 테스트 30건과 하위 사례 10건이 통과했다. 생성기가 만든 합성 VM/OKE 두 앱의 JSON 세 파일을 Companion의 실제 AgentConnectionRegistry 및 OkeWorkloadHealth.Target으로 읽는 Java 계약 테스트도 통과했다. 레지스트리 간 앱 ID·인증 참조·clusterId 연결과 다른 구획에서 목록이 비어 있는 것을 검사했다. 실제 토큰·kubeconfig는 읽지 않았다. 이 검증은 새 인프라 배포 완주나 운영 권한 검증을 대신하지 않는다.
