# VM에서 검증한 에이전트를 OKE에서도 실행하기

OCI 엔지니어가 같은 service-desk 에이전트를 Kubernetes 환경에 배포하고, Companion에서 배포 결과를 확인하며 Langfuse에서 실행을 추적하도록 하는 다음 단계 설계다. **2026-11-08 현재 OKE 미배포**이며 아래 내용은 구현·실측할 계약이다. 기존 VM 배포 경로는 유지한다.

## 역할과 경계

Companion은 OCI DevOps 실행·상태 조회와 외부 도구 연결을 제공한다. 앱의 DB 계정, Agent Memory 설정, Langfuse 비밀 키를 Companion 코드에 넣지 않는다. 에이전트 플랫폼과 Companion은 별도 프로젝트로 유지한다.

| 구성 | 맡는 일 | 첫 OKE 검증 |
|---|---|---|
| OCI DevOps / OCIR | 이미지 빌드·보관, OKE 배포 실행 | 이미지 digest와 빌드 출처 연결 |
| OKE Enhanced cluster | 앱 Pod 실행, Kubernetes ServiceAccount 기반 OCI 인증 | 별도 namespace 및 최소 권한 |
| 앱 Deployment / Service | HTTP API 실행 및 클러스터 내부 접근 | 1 replica, Recreate, 외부 공개 없음 |
| PVC / OCI Block Volume | 현재 SQLite 업무 데이터 보존 | 1 replica 전용, 재스케줄 검증 |
| 기존 ADB / Oracle Agent Memory | 장기 기억 저장·검색 | VM 데이터와 구분한 namespace |
| OCI Generative AI | 채팅 모델 및 임베딩 | 두 호출 경로 모두 workload identity |
| 기존 Langfuse | 실행 추적·입출력·오류 관측 | 비공개 연결, OKE 환경 식별 |
| OCI Vault / 비밀 주입 | DB·Langfuse 등 런타임 비밀 공급 | 이미지·Git·Terraform 변수에 평문 포함 금지 |
| Companion | 성공 빌드와 대상 대조, 실행, 결과·관측 링크 | 범용 OKE 지원 추가 필요 |

흐름은 Companion → OCI DevOps → OCIR 이미지 digest → OKE Pod → OCI 모델·ADB·Langfuse다. Companion이 에이전트를 직접 실행하거나 관측 데이터를 자체 저장하는 구조가 아니다.

## VM 코드를 그대로 복제할 수 없는 부분

0.6.0 릴리스는 `DESK_OCI_AUTH=oke`를 명시적으로 선택하는 공통 클라이언트 생성 경로를 모델과 임베딩 양쪽에 연결했다. 선택한 인증이 실패하면 VM 인증이나 로컬 API 키로 자동 우회하지 않는다. 기존 VM 기본값은 유지한다.

Oracle Python SDK의 OKE signer를 사용한다. workload identity는 Enhanced cluster를 전제로 계획하며 클러스터·namespace·ServiceAccount를 IAM 조건으로 제한한다. OCI 모델 호출 리전과 OKE 실행 리전은 별도 입력이다. 실제 설치한 SDK 버전의 signer 및 서비스 지원을 배포 전에 확인한다.

근거: [Oracle Python SDK 인증 문서](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/signing.html), [Oracle OKE workload identity와 Vault 구성 설명](https://blogs.oracle.com/cloud-infrastructure/oci-vault-access-from-oke-workloads).

SQLite는 앱의 업무 상태 저장소이며 ADB의 장기 기억 저장소와 역할이 다르다. 첫 검증은 PVC와 1 replica로 제한하고 업데이트는 Recreate로 수행한다. 다중 replica나 HPA를 켜기 전에 업무 저장소를 공유 DB로 전환하고 마이그레이션·동시성·중복 처리 검증을 별도로 수행한다. PVC 1개를 여러 Pod에 붙이는 것만으로 운영 구성이 완성되지 않는다.

## 필수 입력과 선택 입력

| 입력 | 필수 여부 | 검증 |
|---|---|---|
| region / compartment / cluster ID | 필수 | 실제 대상 일치, ACTIVE 상태 |
| namespace / ServiceAccount | 필수 | IAM 및 배포 대상과 일치 |
| image digest / source build ID | 필수 | 가변 latest 태그 금지, 성공 빌드와 연결 |
| 모델 리전·구획·모델 ID | 필수 | OKE 인증으로 실제 호출 |
| 메모리·Langfuse 비밀 참조 | 필수 | 참조만 관리, 본문 출력 금지 |
| memory namespace | 필수 | 기존 VM 합성 데이터와 격리 |
| PVC 크기 / storage class | 필수 | 영구 볼륨 생성·재마운트 확인 |
| CPU·메모리 requests/limits | 필수 | 첫 실측 후 조정, 임의 HA 주장 금지 |
| replicas | 초기 1 고정 | 공유 DB 검증 후 다중 구성 허용 |
| ingress / TLS | 선택, 기본 미공개 | 외부 공개 시 별도 인증·TLS 구성 |
| 모델·관측 검사 제한 시간 | 선택 | 유한 시간, 실패를 성공으로 숨기지 않음 |

ADB 접근 ACL에는 실제 OKE 송신 경로를 반영해야 한다. Pod 주소를 추측해 추가하지 않는다. Langfuse 비공개 LB까지 라우트·보안 규칙·DNS를 검증한다. 기존 VM 경로의 ACL과 IAM은 보존한다.

## 구현 및 완료 기준

1. VM 기동 후 현재 릴리스·모델·메모리·Langfuse 검사를 재확인한다. 복구 시 앱 바이너리 복구와 DB 데이터 복구가 별개임을 기록한다.
2. 인증 공통 경로와 테스트를 먼저 구현한다. 모델과 임베딩이 실제로 같은 선택을 전달받는 연결 테스트를 포함한다.
3. 고정 의존성으로 비root 컨테이너를 만들고 OCIR digest를 확보한다. 런타임 비밀은 이미지에 포함하지 않는다. 컨테이너 시작·종료 및 쓰기 경로를 검사한다.
4. OKE와 네트워크·권한·비밀 주입을 Terraform 입력으로 준비한다. 현재 SDK/리소스 스키마를 확인한 후 설계를 코드로 옮긴다.
5. Kubernetes 명세에 단일 Deployment, ServiceAccount, 내부 Service, PVC, startup/readiness/liveness 검사를 둔다. liveness에 모델·DB 외부 장애를 연결해 재시작 폭풍을 만들지 않는다. 업무 준비 상태는 별도로 확인한다.
6. Companion은 범용 OKE 단계의 대상 확인·실행·상태 조회를 지원한다. 기존 단일 VM 단계 검증을 느슨하게 만들어 OKE를 무조건 허용하지 않는다. namespace·cluster·digest를 실행 전에 표시한다.
7. 배포 후 같은 합성 검사로 모델, 세션 간 기억, Langfuse 5개 관측 및 입출력 정책을 확인한다. Pod 재생성 후 업무 데이터와 기억이 유지되는지, 이전 digest 복구가 되는지 검증한다.

첫 완료는 Companion에서 OKE 배포를 시작하고 성공 빌드와 digest를 대조하며 위 기능·재시작 검증을 통과한 시점이다. 문서·명세 생성이나 Pod Running만으로 완료 처리하지 않는다. 다중 노드 HA, 부하 시험, 다중 replica, 자동 롤백, 외부 TLS는 별도 후속 검증으로 명시한다.

## 구현 진척과 검증 한계

2026-11-08 소스에 `oci_client.py`를 추가해 모델과 임베딩의 클라이언트 생성을 통합했다. `DESK_OCI_AUTH`는 instance(기본), config, oke를 명시적으로 지원하며 OKE 인증 실패를 다른 인증으로 우회하지 않는다. 이 변경이 포함된 0.6.0을 OCI Functions에서 빌드하고 Companion을 통해 VM에 배포했다. VM의 모델·메모리·Langfuse 검사까지 통과했다. OKE에는 같은 검증 산출물을 컨테이너로 포장하되 workload identity는 별도 실측한다.

인증 선택, 실패 시 우회 금지, 모델·임베딩의 입력 연결을 테스트한다. 선택적 메모리 패키지가 없는 로컬에서는 해당 import만 테스트 대역으로 대체하고 인증 팩터리 진입에서 종료한다. 실제 OKE 토큰 교환이나 OCI 권한 성공을 증명하는 테스트는 아니다. 클러스터·컨테이너 배포·Companion의 범용 OKE 대상 검증·실행 코드는 구현하고 로컬 테스트를 통과했지만 실제 OKE 배포 실행은 아직 검증하지 않았다. Kubernetes 명세 생성기는 구현했으며 입력 차단과 단일 Pod·비밀 참조 계약을 로컬에서 검증했다. 사용 방법과 남은 적용 조건은 [OKE 명세 준비](OKE-MANIFESTS.md)를 참조한다.

프로비저닝 용량은 [설치·작업 공간 산정](CAPACITY.md)을 먼저 적용한다. 노드 이미지 저장 공간, Pod 임시 저장 공간, PVC 데이터 용량을 분리하며 여유 공간만 보고 기존 관측 서버에 빌드를 공존시키지 않는다.

## 전용 OKE 인프라 구현 계약

첫 클러스터는 기존 `document_search`와 분리하고 전용 VCN, Enhanced cluster, AMD64 관리형 노드 풀을 만든다. Kubernetes API와 노드는 모두 비공개 서브넷에 둔다. OCI 서비스에는 Service Gateway, 외부 이미지·업데이트에는 NAT Gateway를 사용한다. API 6443/12250 접근은 전용 VCN 내부로 제한하고 노드 간 트래픽과 API→kubelet 통신만 내부에서 허용한다. DevOps private network channel과 운영자의 비공개 접근 경로는 별도 연결해야 하며, 이 단계에서 API 공개 주소나 외부 앱 LoadBalancer를 만들지 않는다.

Terraform 입력은 리전·구획·VCN CIDR·버전·지원 노드 이미지·shape·가용 도메인·노드 수·노드 디스크 예산이다. 메모리 설정과 비밀값은 넣지 않는다. 이미지 교체/운영체제/로그/임시 작업/여유를 합한 예산보다 부트 볼륨이 작으면 계획을 차단한다. 첫 1노드·1Pod는 기능 검증용이며 HA를 의미하지 않는다. ADB 송신 ACL, Langfuse 피어링, workload IAM, Vault 주입, PVC와 배포는 후속 연결이다.

## 실제 준비 결과 (2026-11-08)

전용 비공개 클러스터와 1개 노드는 OCI API에서 ACTIVE이며 인프라 Terraform 적용을 완료했다. Kubernetes Ready와 실제 노드 파일시스템 여유는 별도 확인이 필요하다.

Companion에서 실행한 세 번째 컨테이너 빌드가 SUCCEEDED이고 OCIR 게시를 완료했다. Functions 소스 빌드 `b874b66b-9c95-43b5-a0c1-8c07a32d8afe`의 0.6.0 패키지를 사용했다. 고정 이미지 digest는 `sha256:582a4752781f2be864542f8644e81855a3a08650069dd7f0edfac6f1ef6c6c2d`다. 컨테이너 기본 명령으로 기동하여 `/health` 200과 버전 0.6.0을 확인했다. 합성 인증·모델 설정을 사용했으며 외부 모델·ADB·Langfuse는 이 검사에서 확인하지 않았다.

비공개 DevOps 배포 환경과 전용 파이프라인은 [별도 Terraform 구성](../infra/terraform/oke-delivery/README.md)으로 관리한다. 앱 배포 단계는 비밀 주입·권한·통신 준비 후 추가한다.

2026-11-08 후속 확인: Bastion은 테넌시 할당량으로 생성하지 못해 기존 관측 서버와의 비공개 피어링을 구성했다. API 인증서 검증을 유지한 운영 터널로 Kubernetes 노드 Ready를 확인했다. 100GB 부트 볼륨의 실제 루트는 처음 29.4GiB였고, 확장 후 82.8GiB/여유 71.3GiB를 확인했다. 노드 초기화 템플릿에도 자동 확장과 실제 용량 검사를 추가했다. 임시 관리자 Pod는 삭제했다. **앱 배포, Secret·IAM, ADB·Langfuse 실제 연결 검증은 여전히 미완료**다.
