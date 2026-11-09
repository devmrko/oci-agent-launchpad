# OCI Agent Launchpad · 0.1.0-alpha.1

고객과 OCI 엔지니어가 작은 에이전트를 함께 만들고, OCI에 배포해 실제 동작과 관측을 확인하는 **엔지니어 동행형 알파**입니다. 고객은 실행 코드, 환경 설정, 검증 결과와 운영 전 보완 목록을 받습니다.

**현재 상태: 공개 저장소의 알파 릴리스 초안.** 준비된 환경에서 Hello Agent 완주를 확인했습니다. 새 고객 환경 자동 설치와 운영 서비스 제공은 아직 검증하지 않았습니다. Python Foundation 등 별도 의존성의 접근 권한과 OCI 실행 환경은 따로 준비해야 합니다. [버전 명세](releases/0.1.0-alpha.1.json)는 서로 독립적인 저장소의 조합을 고정하며 각 제품의 패키지 버전을 바꾸지 않습니다.

## 무엇이 필수인가

| 구성 | 이번 기본 알파 | 담당 역할 | 에이전트 실행과의 관계 |
|---|---|---|---|
| Launchpad | 필수 | 인터뷰·설계·예제·배포 도구·인수 자료 | 배포 후 요청 경로에 없음 |
| OCI Companion | **필수** | 빌드·배포 실행, 앱 등록, 상태 조회 | 꺼져도 이미 배포된 앱은 독립 실행 |
| Python Foundation | 기본 예제 필수 | 앱 인증·웹 공통 코드 | 앱 패키지 의존성 |
| OCI Functions / DevOps / OCIR | 기본 빌드·배포 경로 필수 | Python 소스 빌드, 이미지 패키징, 전달·배포 | 실행 중 요청마다 빌드 서비스를 호출하지 않음 |
| OKE / OCI Generative AI | 기본 실행 경로 필수 | 앱과 모델 실행 | 업무 요청 처리에 필요 |
| Langfuse | 기본 예제의 관측·인수에 필수 | 모델·도구·응답 추적 | 장애가 도구 응답의 직접 성공 조건은 아니지만 관측 합격은 실패 |
| Oracle Agent Memory / ADB | 업무에 따라 선택 | 세션을 넘어 보존할 기억 | Hello Agent에는 사용하지 않음 |
| API Gateway / ContextForge / OPA | 요구에 따라 선택·후속 통합 | 진입점·도구 중계·정책 | 설치·통합 완료로 간주하지 않음 |

Companion은 플랫폼 코드를 포함하는 런타임이 아닙니다. 연결 주소·인증 참조·OCI 자원 관계를 관리합니다. 운영용 Companion을 상시 제공할 위치와 접근 권한은 고객별로 결정합니다. 현재 기본 화면은 관리자 PC의 loopback 접속을 사용합니다.

## 첫 성공까지의 경로

**업무 합의 → Companion 빌드 → OCI 이미지/배포 준비 → Companion 배포 → 웹 시험 → Langfuse 확인 → Companion 상태 조회 → 검증 결과 인수**

1. [업무 입력 양식](templates/use-case.md)으로 사용자, 목적, 대표 질문, 성공 조건과 제외 범위를 정합니다. 처음에는 Hello Agent의 “지금 서울 몇 시인가요?”를 합성 사례로 사용합니다.
2. 엔지니어가 아래 필수 입력과 IAM·네트워크·처리 공간을 사전 점검합니다. [용량 기준](deploy/CAPACITY.md), [배포 IAM](deploy/PIPELINE-IAM.md)을 확인합니다.
3. 버전 명세의 고정 커밋을 사용합니다. [Functions 준비 절차](deploy/FUNCTIONS.md)는 작업 이력을 포함하므로, 현재 Hello Agent 상태는 [인수 기록](examples/hello-agent/DELIVERY.md)을 기준으로 봅니다. Functions는 앱과 Foundation wheel을 빌드합니다. 별도 Managed Build는 이미지 패키징을 담당합니다.
4. 엔지니어가 사설 Registry·배포 환경·명세·필요한 Secret 참조를 준비합니다. 현재 이 연결 준비는 수작업과 Launchpad 도구가 섞여 있습니다. [OKE 명세 안내](deploy/OKE-MANIFESTS.md)와 `deploy/render_hello_oke.py`를 사용하며 Service Desk용 값을 그대로 적용하지 않습니다.
5. Companion 배포 화면에서 대상 클러스터·namespace·이미지 digest를 확인하고 실행합니다. 배포 SUCCEEDED만으로 업무 검증 완료로 보지 않습니다.
6. 승인된 사설 접속 경로로 Hello Agent 웹을 열고 합성 계정으로 질문합니다. 실제 OCI 모델·도구 응답과 trace ID를 확인합니다. 모델 데이터 처리 리전은 런타임 리전과 별도로 확인합니다.
7. Langfuse에서 해당 trace의 모델·도구·응답 입력/출력을 확인합니다. Companion에는 앱을 독립 등록하고 health·버전·OKE Pod 상태를 확인합니다. [연결 설정 생성 안내](deploy/COMPANION-CONNECTIONS.md)를 따릅니다.
8. 준비된 검증 Job은 Companion에서 실행할 수 있습니다. 종료 상태와 결과 JSON은 현재 엔지니어가 별도로 수집해 인수 자료에 넣습니다. Job마다 고유 이름을 쓰고 실행 ID·Job UID를 보존합니다.

이 절차는 새 테넌시를 자동 구성하는 설치 마법사가 아닙니다. 관리자 전제 조건이 충족되지 않으면 먼저 누락을 해결합니다. 기존 시험 환경의 OCID·계정·Registry 접근 권한이 고객에게 자동 제공되지는 않습니다.

## 환경 입력과 설정 요약

| 입력 | 필수/조건부 | 설정·확인 위치 |
|---|---|---|
| OCI profile, tenancy, compartment, runtime region | 필수 | Companion 연결과 OCI SDK 설정; 비밀 키를 Git에 넣지 않음 |
| model region, model ID, model compartment | 필수 | `render_hello_oke.py` 입력; 처리 위치와 모델 권한 확인 |
| OKE cluster, namespace, ServiceAccount | 필수 | 배포 환경·Kubernetes 명세·workload IAM |
| private subnet, 관리 접속 경로, DNS/TLS | 필수 | OCI 네트워크와 관리자 연결; TLS 검증을 끄지 않음 |
| image digest, OCIR pull Secret | 필수 | 배포 명세; 접근 가능한 이미지 위치를 별도 준비 |
| 앱 토큰·Langfuse 프로젝트 키 | 필수 | 보호된 Secret/파일; UI에는 인증 참조만 등록 |
| Functions 입력 객체 버전·SHA-256·고정 소스 | 필수 | Companion Python 빌드 입력 |
| 배포 pipeline, environment, artifact | 필수 | OCI DevOps와 Companion 실행 전 확인 |
| 앱 주소·인증 참조·OKE 조회 연결 | 필수 | Companion 연결 설정; 서버에서 실제 도달 가능해야 함 |
| 메모리 DB·사용자 경계·보존/삭제 | Memory 선택 시 필수 | Oracle Agent Memory 구성; 이번 Hello 경로에는 없음 |
| 예산·비용 담당자·지원 담당자 | 필수 | 고객 인수 기록; 구체적 금액은 고객별 확정 |

## 알파 합격과 제한

기본 사례에서 웹 응답, 동일 trace의 관측 입출력, Companion 앱/Pod 상태, 검증 Job 결과가 확인되면 기술 파일럿의 첫 성공입니다. 고객 업무의 운영 인수는 별도 기준으로 판단합니다.

- 실제 검증: [웹·Companion 기록](examples/hello-agent/verification/browser-2026-11-09.json), [Companion Job 기록](examples/hello-agent/verification/companion-job-2026-11-09.json).
- Companion 고정 커밋의 깨끗한 체크아웃: 156개 테스트와 패키징 통과. 최신 원격 브랜치 전체를 자동 보장하지 않습니다.
- 미완료: 새 환경 독립 설치 재현, 기본 OKE 경로 복구·정리 실습, OSS 배포 조합 전체 고정, Job 결과 자동 수집, 고객용 인증, 관측 실패 재전송.
- 운영 전제: 합성 데이터·시험 계정으로 시작합니다. 현재 데모 인증과 입력/출력 수집 정책을 그대로 운영에 가져가지 않습니다.
- 비용 정리: 생성한 자원 목록과 소유자를 인수 자료에 남깁니다. 공유 OKE·관측·DB 자원을 일괄 삭제하지 않습니다. 검증 Job TTL은 다른 OCI 자원 비용을 정리하지 않습니다.

[출시 조건과 다음 보완 순서](docs/design/alpha-readiness.md)를 확인하십시오. 이 알파는 AgentCore 전체 기능의 완전 동등성을 약속하지 않습니다.
