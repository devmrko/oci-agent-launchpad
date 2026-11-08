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

## 아직 이 구성에 포함하지 않은 부분

파이프라인은 이 단계에서 비어 있다. 런타임 Secret, OCIR pull 인증, workload IAM, ADB·Langfuse 네트워크 연결을 준비한 뒤 고정 이미지 digest를 사용하는 명세와 OKE 배포 단계를 추가해야 한다. 환경이 ACTIVE여도 Kubernetes 권한이나 앱 실행 성공을 입증하지 않는다.

앱 배포 명세는 [OKE 명세 생성기](../../../deploy/OKE-MANIFESTS.md)를 사용한다. 초기 앱은 PVC와 단일 replica를 사용한다. 실제 배포 및 모델·메모리·관측 검증이 완료돼야 OKE 지원 검증을 완료 처리한다.
