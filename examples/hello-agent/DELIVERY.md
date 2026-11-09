# Hello Agent OCI 완주 조건

이 예제의 목적은 Companion을 통한 빌드·OCI 배포·실제 에이전트 실행·관측을 처음부터 끝까지 보여주는 것입니다. 로컬 CLI는 선행 시험일 뿐 완료 결과가 아닙니다.

## 완료 조건

1. 독립 앱으로 소스를 고정하고 Companion에서 Functions 빌드를 실행합니다.
2. 빌드 산출물과 해시를 확인하고 OCI 배포 대상으로 전달합니다.
3. 서울의 기존 프로젝트용 OKE에 별도 workload로 배포합니다. 기존 Service Desk를 덮어쓰지 않습니다.
4. 웹에서 인증 후 질문하면 실제 OCI 모델이 시간 도구를 선택하고 OCI 런타임에서 실행합니다.
5. 같은 실행의 모델 입력·출력, 도구 입력·결과, 응답을 Langfuse에서 확인합니다.
6. Companion에 독립 앱으로 등록하고 health·배포 버전·실행 대상을 확인합니다.
7. 사용자에게 접속 방법, 실행 결과, Companion·Langfuse 확인 위치를 전달합니다.

메모리 저장은 시간 조회 업무에 필요하지 않으므로 제외합니다. 이 제외는 운영 배포·관측을 생략한다는 의미가 아닙니다. 모델 처리는 기존 허용 리전 설정을 사용하고 서울 런타임과 구분합니다.

## 확인한 상태와 남은 작업

2026-11-09 확인 기준입니다. 배포 성공과 업무 실행, 관측 조회, 고객 접속을 별개로 판정합니다.

| 단계 | 상태 | 확인 근거와 한계 |
|---|---|---|
| Python 빌드 | 성공 | Companion에서 OCI Functions 실행, 앱 테스트 8개와 하위 사례 5개 통과, wheel 다운로드 해시 확인 |
| 이미지 패키징 | 성공 | Companion에서 Managed Build 실행, 런타임 import·health 검사 후 사설 OCIR 등록 |
| OKE 배포 | 성공 | Companion 배포 실행, 명세 적용 및 Deployment 상태 확인 SUCCEEDED |
| OCI 모델과 도구 | 성공 | OKE 내부 Job에서 인증된 `/api/chat` HTTP 200, 실제 모델이 get_time/서울 선택, 도구가 서울 시각 반환 |
| 인증 | 기본 경계 확인 | 무인증 요청 거부. 운영용 사용자 인증·권한 검증은 아님 |
| 관측 전송 | 성공 | 실행 응답의 telemetry=exported. 저장·조회 성공과 별개 |
| 관측 조회 | 성공 | Observations API v2 HTTP 200, AGENT·GENERATION·TOOL 각각 입력·출력 존재 확인 |
| 브라우저 접속 | 성공 | SSH와 kubectl port-forward를 거쳐 웹에서 인증 호출, 실제 모델·도구 응답 확인. 운영 고객 접속 경로는 아님 |
| Companion 앱 등록 | 성공 | 별도 앱 Hello Agent · OKE 등록, UP·0.1.0, Pod Ready 1·재시작 0, 노드 Ready 확인 |

애플리케이션 버전은 0.1.0이며 이미지 digest는 `sha256:44f64c7dec630e56115d89fccbce63c56e09fdee4a1719d49a45e81005ab4582`입니다. 소스 빌드는 `7d4817c8a70b4eb6964ed31ffbf7120a0c5f2866`을 고정했습니다. 원본 실행 결과는 운영자 로컬 `.run/oci-launchpad/hello-*.json`에 보관하며 비밀값·환경별 설정은 Git에 올리지 않습니다.

## 배포 구성

- 기존 서울 OKE의 namespace에 별도 `hello-agent` Deployment·ClusterIP Service·ServiceAccount를 만듭니다. 기존 Service Desk의 selector나 Deployment를 재사용하지 않습니다.
- `deploy/render_hello_oke.py`는 namespace, digest 고정 image, service_account, runtime_secret, image_pull_secret, model_region, model_compartment, model_name을 입력받습니다.
- 컨테이너는 비루트 사용자, 읽기 전용 루트 파일시스템, CPU 250m/1 및 메모리 256Mi/768Mi 요청/한도로 실행합니다. 임시 공간은 64Mi입니다. DB·PVC는 만들지 않습니다.
- 기존 합성 데모용 Secret에서 접근 토큰과 Langfuse URL·프로젝트 키만 투영합니다. DB 암호·wallet·메모리 설정은 주입하지 않습니다. 고객별 토큰 분리와 OIDC는 운영 전 보완 항목입니다.
- 전용 workload 권한은 선택한 클러스터·namespace·ServiceAccount·모델의 채팅 호출에 한정합니다.
- 검증 Job은 별도 ServiceAccount로 앱을 호출합니다. 최초 원격 검증은 지정 Object Storage 객체 생성 권한을 사용했고 검증 후 회수했습니다. 이후 Companion에서 실행한 검증은 `HELLO_PROBE_OUTPUT=stdout`으로 결과를 남겨 추가 IAM 권한이 필요 없습니다. 이 모드에서는 ServiceAccount 토큰 자동 마운트를 끕니다. 결과에는 합성 질문의 응답과 trace ID, 검사 결과만 포함합니다.

## Companion에서 되는 작업과 부족한 부분

Functions 빌드, 컨테이너 빌드 및 원본 앱의 OKE 배포는 Companion 화면에서 실행했습니다. 최초 일회성 검증 Job은 당시 Companion의 지원 kind에 없어 OCI DevOps API로 실행했습니다. 이후 Companion에 제한된 batch/v1 Job 검사를 추가했습니다. Job 이름·ServiceAccount·기한·재시도·TTL·Secret 참조를 실행 전에 표시하며 배포 상태와 업무 검증 미확인을 구분합니다. 실제 Job 종료 상태와 검사 JSON을 화면에 자동 수집하는 기능은 아직 없습니다.

Job 지원 시에는 Job을 무조건 허용하지 않고 namespace, 이미지 digest, ServiceAccount, Secret 참조, 실행 기한, 재시도 횟수, 결과 위치를 검증해야 합니다. 화면에서도 **앱 배포 성공**과 **검증 Job의 실제 검사 성공**을 분리해야 합니다. 일반 OKE 배포 단계가 Job 명세를 적용한 것만으로 업무 검증 성공을 판정하면 안 됩니다.

## IAM 한도에서 얻은 교훈

새 정책 생성과 기존 정책에 한 줄을 추가하는 두 시도 모두 `PolicyStatementsLimitPerCompartmentChainExceeded`로 거절됐습니다. 해당 시점 OCI 응답은 한도 1,446, 사용 1,452였습니다. 이 값은 이 테넌시에서 받은 오류의 관측값이며 모든 OCI 환경의 기본값이 아닙니다. [공식 문서](https://docs.oracle.com/en-us/iaas/Content/Identity/policymgmt/policy-limits-compartment-hierarchy.htm)는 루트부터 해당 컴파트먼트까지의 문장을 함께 계산한다고 설명합니다.

프로젝트의 기존 배포 정책에서 동일 권한을 파이프라인 ID마다 반복하던 문장을 `where any {명시적 ID 조건들}`로 통합했습니다. 원본을 보관하고 권한·대상 ID 쌍의 집합이 정확히 같은지 확인한 뒤 38문장을 7문장으로 줄였습니다. 이후 기존 Hello Agent 정책에 결과 객체 생성 권한을 추가하는 데 성공했습니다. 다른 프로젝트 정책은 수정하지 않았습니다.

`infra/terraform/release/main.tf`와 `deploy/prepare_pipeline_iam.py`도 동일한 방식으로 수정했습니다. 재적용 전 실제 정책과 Terraform state를 새로 읽고 계획을 검토해야 합니다. 구형 문장 형식은 마이그레이션 입력으로 받아들이되 대상 ID를 누락한 입력은 거부합니다.

## 접속과 관측의 주의점

관측 VM은 RUNNING이고 SSH 서비스가 활성 상태였지만 관리 PC에서 연결이 거절되거나 시간 초과됐습니다. 현재 관리 IP가 기존 허용 IP와 달라 해당 VM NSG에 임시 /32 규칙을 추가했으나 해결되지 않았고 임시 규칙은 제거했습니다. 내부 진단 계정은 sudo 권한이 없어 호스트 방화벽 상태를 읽지 못했습니다. Bastion 추가는 테넌시 할당량 오류로 실패했습니다. 이후 관리 PC의 외부 IP가 바뀐 환경에서 해당 IP /32 SSH 규칙을 추가하자 로그인에 성공했습니다. 이전 실패 원인은 단정할 수 없습니다. 현재 경로는 SSH → 사설 OKE API → localhost port-forward이며 앱을 공개 인터넷에 노출하지 않았습니다. 관리 IP가 바뀌거나 터널이 종료되면 다시 연결해야 합니다. 고객 운영은 VPN/내부 진입점과 정식 인증으로 별도 구성해야 합니다.

Langfuse v4에서는 OTLP 전송 성공만으로 조회 완료를 판단하지 않습니다. 검증은 [Observations API v2](https://langfuse.com/docs/api-and-data-platform/features/public-api)에 traceId·시간 범위·core,basic,io 필드를 지정하고, 모델·도구·루트 observation의 입력과 출력을 확인합니다. 첫 검증의 구형 API 선택 오류를 수정했습니다.

## 운영 전 보완

실패한 모델 호출 추적, 관측 재전송·유실 방지, 고객별 인증·권한·비밀 회전, TLS와 내부 접근 경로, 부하·비용 제한, 장애 복구·롤백 검증은 남아 있습니다. 현재 결과는 작은 OCI 실행 예제의 검증이며 고객 운영 서비스 완성을 의미하지 않습니다.

## 최종 클라우드 검증 결과

[2026-11-09 OKE 검증 JSON](verification/oke-2026-11-09.json)의 모든 검사 항목이 PASS입니다. 실제 응답은 “서울의 현재 시간은 2026-11-09T14:57:38+09:00입니다.”였으며 trace ID는 `30c3b2b0a21b7599fb22013e34c43340`입니다. health, 무인증 거부, 모델·도구 실행, OTLP 전송, Langfuse 세 observation의 입력·출력을 확인했습니다. 브라우저 화면 검증은 이 결과에 포함하지 않습니다.

검증 후 배포 단계는 Companion이 지원하는 원본 앱 명세 3개로 복원했고, 일회성 결과 객체 생성 권한을 제거했습니다. 검증 Job은 완료 후 자동 정리하도록 TTL을 설정했습니다. 단계 설정 변경 직후 실행한 일부 검증 배포에는 Job이 포함되지 않았으므로, 실행 로그에서 적용한 명세를 확인하고 다섯 명세가 반영된 실행의 결과로만 합격을 판정했습니다.

관련 로컬 검증: IAM 권한 동등성·구형 입력 마이그레이션·OKE 명세 분리·Langfuse v4 조회 계약 테스트 26개 및 하위 사례 2개 통과, Terraform release 모듈 validate 통과.

## 브라우저와 Companion 검증

[브라우저 검증 결과](verification/browser-2026-11-09.json)는 2026-11-09 웹에서 “지금 서울 몇 시인가요?”를 실행한 결과입니다. 서울 시각 15:11:48을 반환했고 trace ID `db02cedcc30d15f20fb1f59d6557c80b`의 AGENT·GENERATION·TOOL 입력/출력을 Langfuse API로 각각 확인했습니다. 이 결과는 앞선 내부 Job 결과와 별개로 보관합니다.

운영자 Mac의 현재 접속 주소는 Hello Agent `http://127.0.0.1:18093/`, Companion `http://127.0.0.1:8091/agents/connections`입니다. 이 주소는 SSH/API 터널과 kubectl 포트 전달 프로세스가 살아 있는 이 Mac에서만 유효합니다. 다른 고객의 공용 URL이 아닙니다. 토큰은 승인된 합성 계정 참조로 공급하며 문서·Git·URL에 넣지 않습니다.

Companion 등록 앱에서 Hello Agent를 선택하면 앱 health와 OKE Deployment/Pod/노드 상태를 따로 봅니다. Hello Agent에는 메모리 의존성이 없으므로 ADB를 등록하지 않았습니다. 여러 앱이 동일 클러스터를 사용해도 각 Deployment 소유 Pod만 표시합니다.

알파 제공 범위와 미완료 기준은 [알파 출시 판단](../../docs/design/alpha-readiness.md)을 참고하십시오.

## Companion에서 검증 Job 실행 확인

[Companion Job 검증 결과](verification/companion-job-2026-11-09.json)에 실제 실행 ID·Job UID·probe SHA-256을 기록했습니다. Companion 화면에서 `hello-validation-012`의 240초 기한·재시도 0회·TTL 3600초·참조 Secret을 확인하고 실행했습니다. OCI 배포 SUCCEEDED, Kubernetes Job Complete, health·무인증 거부·실제 모델/도구·OTLP·Langfuse 입출력 모두 PASS였습니다. 실제 응답 시각은 15:23:26, trace ID는 `89b30c83950cdd54285b69920a580c69`입니다.

Companion 화면은 배포 SUCCEEDED와 업무 검증 미확인을 구분합니다. 이번 Job 종료 상태와 JSON 결과는 운영자 도구로 읽어 기록했으며 Companion 자동 결과 수집은 미구현입니다. 검증 후 파이프라인은 원래 앱 명세로 복원했습니다. 완료된 Job은 TTL로 정리됩니다. 새로운 검사에는 고유한 Job 이름을 준비해야 합니다.

검증: Companion 전체 159개 테스트 통과, probe 출력 방식·실패 종료·Langfuse 조회 계약 3개 테스트 통과. Companion과 Launchpad는 각각 독립 저장소에서 변경하고 특정 앱 코드나 관측 DB를 Companion에 포함하지 않습니다.
