# Companion에서 사용할 비공개 OKE 배포 대상 준비

OCI 엔지니어가 인터넷에 Kubernetes API를 공개하지 않고 DevOps에서 OKE로 배포할 수 있도록 배포 환경과 전용 파이프라인을 만든다. Companion은 이 파이프라인을 조회하고 실행한다. 에이전트의 비밀값이나 제품 전용 설정은 Companion에 넣지 않는다.

## 필수 입력

| 변수 | 역할 |
|---|---|
| region | OKE와 DevOps 리전 |
| project_id | 기존 DevOps 프로젝트 |
| cluster_id | 기존 OKE 클러스터 |
| private_subnet_id | Kubernetes API에 접근할 수 있는 비공개 서브넷 |
| name | 선택. 기본 launchpad-service-desk-oke |

이 서브넷에 DevOps private endpoint가 만들어진다. 서브넷 라우팅과 보안 규칙에서 API 연결을 허용해야 한다. 실행 계정에는 DevOps 리소스와 private endpoint 생성 권한이 필요하다. [Oracle 구성 안내](https://docs.oracle.com/en-us/iaas/Content/devops/using/create_oke_environment.htm)를 참고한다.

```sh
terraform -chdir=infra/terraform/oke-delivery init
terraform -chdir=infra/terraform/oke-delivery validate
terraform -chdir=infra/terraform/oke-delivery plan -var-file=/absolute/path/oke-delivery.tfvars.json -out=/absolute/path/oke-delivery.tfplan
terraform -chdir=infra/terraform/oke-delivery apply /absolute/path/oke-delivery.tfplan
```

실제 입력, state와 계획 파일은 Git에 넣지 않는다. 기존 state를 보존해 후속 변경에 사용한다.

## 앱 배포와 별도 준비 사항

`manifest_files`를 비워 두면 배포 대상만 만든다. 명세 파일 경로 목록과 `workload`를 지정하면 inline artifact와 OKE 배포 단계를 만든다. 파일 순서는 Namespace → ServiceAccount → PVC → Deployment → Service로 지정한다. Secret 값은 명세나 Terraform state에 넣지 않는다. 환경이 ACTIVE여도 앱 실행 성공을 입증하지 않는다.

앱 배포 명세는 [OKE 명세 생성기](../../../deploy/OKE-MANIFESTS.md)를 사용한다. 초기 앱은 PVC와 단일 replica를 사용한다. 실제 배포 및 모델·메모리·관측 검증이 완료돼야 OKE 지원 검증을 완료 처리한다.

## 운영 접근 옵션과 이번 환경의 제약

`operator_access`는 선택 입력이며 기본 null이다. 지정하면 `compartment_id`와 비어 있지 않은 `client_cidrs`(/32만 허용)를 받아 세션 최대 1시간의 OCI Bastion을 만든다. 2026-11-08 실제 생성은 테넌시 Bastion 할당량 초과(QuotaExceeded)로 실패했다. 실패한 Bastion은 생성되지 않았고 실제 변수에서 이 옵션을 제거했다. 다른 Bastion을 삭제하거나 공개 API로 우회하지 않았다.

이번 검증은 기존 관측 서버와 OKE 간 피어링을 사용했다. DevOps private endpoint 배포 환경과 파이프라인, 앱 배포 단계는 생성했다. 2026-11-08 Companion에서 시작한 실제 앱 배포가 SUCCEEDED로 완료됐다. 운영 접근 경로와 DevOps 배포 경로는 별개다.

## 권한을 나누는 이유

배포 파이프라인은 Kubernetes 명세를 적용하고, 앱 Pod는 모델을 호출한다. 두 주체의 권한을 섞지 않는다.

- 배포 IAM: 해당 파이프라인 하나에 지정 cluster 관리, 지정 project artifact 읽기, 지정 compartment의 `GetSubnet` 호출을 허용한다. API endpoint 서브넷도 조회하므로 private endpoint용 서브넷만 고려하면 안 된다.
- 앱 IAM: `workload`의 cluster·namespace·ServiceAccount 조합에 chat/embedding 모델 호출을 허용한다. `home_region`, `compartment_id`, `namespace`, `service_account`, `chat_model`, `embedding_model`이 필요하다.
- Vault → Kubernetes Secret: [`sync_oke_secret.py`](../../../deploy/sync_oke_secret.py)가 지정 버전을 읽어 표준 입력으로 server-side apply한다. 비밀값을 명령 인수, 로그, last-applied annotation에 남기지 않는다. 자동 회전 컨트롤러는 아니다.
- ADB ACL과 Langfuse NSG·라우팅은 별도로 준비한다. 현재 노드 IP를 허용한 구성은 노드 교체 때 갱신해야 한다.

`target.subnet.id`는 공식 Core Services 지원 변수 목록에서 확인되지 않으므로 사용하지 않는다. GetSubnet 권한은 이 compartment의 서브넷 메타데이터 조회 범위이며, 개별 서브넷 ID 제한이라고 주장하지 않는다. [지원 변수](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Supported_Variables.htm), [일반 변수](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/policyreference_topic-General_Variables_for_All_Requests.htm)를 참고한다.

## 2026-11-08 실제 확인 범위

Companion 화면에서 digest가 고정된 앱 배포를 실행했다. 초기 실행은 `GetSubnet` 404로 명세 적용 전에 실패했다. Audit의 실제 resource ID는 OKE API endpoint 서브넷이었다. IAM 구문이 수락돼도 조건이 실제 요청에서 평가되는지는 별도 확인해야 한다. 지원 변수가 아닌 `target.subnet.id` 조건을 제거하고 지정 파이프라인·compartment·`GetSubnet` 작업으로 제한한 뒤 명세 적용과 배포가 성공했다.

Vault의 runtime/pull Secret 두 개를 namespace에 적용했고 Secret 문서 검증 테스트 5건이 통과했다. 현재 이미지 pull 인증은 기존 운영자 계정에 발급한 토큰이므로 전용 읽기 계정 수준의 최소 권한을 충족했다고 보지 않는다. 운영 전 전용 계정·회전 또는 검증된 workload 기반 pull 방식을 구성해야 한다.

실제 확인 결과:

| 항목 | 관측 결과 |
|---|---|
| Companion → DevOps → OKE | 배포 SUCCEEDED; 명세 5개 적용 |
| Pod / PVC | Ready 1/1, 50GiB RWO Bound |
| 앱 | 0.6.0 health, 미인증 요청 거부 |
| 모델 | OKE workload identity로 OCI 모델 응답과 출처 확인 |
| ADB 메모리 | 저장 후 새 세션에서 같은 메모리 검색 |
| Langfuse | 앱 요청 3건·관측 7건; 모델 입력/출력 존재, 메모리 본문 제외 |
| 재생성 | 새 Pod Ready, 동일 PVC, 기존 요청 기록 3건 보존 |

검증 근거는 로컬 `.run/oci-launchpad/oke-deployment-run.json`, `oke-runtime-check.json`, `oke-observations-check.json`, `oke-persistence-check.json`이다. 환경별 결과 파일과 인증 자료는 Git에 넣지 않는다. 테스트 명령은 `python -m pytest deploy/tests/test_oke.py deploy/tests/test_oke_secret.py -q`이며 15건 통과했다.

단일 노드·단일 replica 검증은 고가용성 검증이 아니다. Companion의 OKE 환경 목록 통합, 상시 모니터 연결, 인증 토큰 회전, 노드 교체 시 ACL 갱신 자동화는 후속 작업이다.

### Inline artifact 인코딩

OCI provider 8.29.0의 INLINE 구현은 `base64encoded_content` 문자열을 바이트로 변환하고 SDK가 전송할 때 인코딩한다. 그래서 이 모듈에는 `file(path)`를 사용한다. `filebase64(path)`를 쓰면 이중 인코딩이 될 수 있다. [고정 버전 provider 소스](https://github.com/oracle/terraform-provider-oci/blob/v8.29.0/internal/service/devops/devops_deploy_artifact_resource.go)의 INLINE 변환과 state 반환 코드를 확인했다. 현재 실제 artifact와 Terraform 비교에서 이 항목의 변경은 발생하지 않았다.
