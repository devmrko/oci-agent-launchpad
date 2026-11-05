# 고객 환경별 OCI 인프라 만들기

리전·구획·이미지·사양을 바꿔 같은 에이전트 기반 인프라를 생성하는 Terraform 템플릿입니다. VCN, 인터넷 게이트웨이, 라우팅, SSH 접근 규칙, VM, 선택적 ADB를 관리합니다. 현재 운영 중인 예제 자원을 자동 인수하지 않습니다.

## Terraform과 커스텀 이미지 역할

Terraform은 네트워크·VM·ADB의 구성과 연결을 관리합니다. 커스텀 이미지는 VM 안의 OS와 공통 실행 환경을 미리 준비할 때 사용합니다. 둘은 함께 사용할 수 있습니다. 초기에는 Oracle Linux 기본 이미지로 시작하고 반복 설치 시간이 문제가 될 때 Packer 등으로 검증된 커스텀 이미지를 만듭니다. 이미지에는 고객 데이터·DB 암호·SSH 개인키·wallet을 넣지 않습니다.

앱 릴리스는 이미지와 분리해 배포합니다. 이미지 변경은 VM 교체를 일으킬 수 있으므로 실행 전 plan을 확인합니다. 기존 예제의 SQLite 업무 DB는 VM에 있으므로 기존 VM을 교체하기 전 별도 영속 볼륨/DB로 옮기는 작업이 필요합니다.

## 입력값

| 구분 | 변수 | 기본값·설명 |
|---|---|---|
| 필수 | `region`, `compartment_id`, `availability_domain` | 배포 위치 |
| 필수 | `image_id` | 해당 리전의 Oracle Linux x86 기본/커스텀 이미지 |
| 필수 | `ssh_public_key`, `ssh_source_cidr` | 공개키 내용, 관리자 공인 IPv4 `/32` |
| 조건부 필수 | `adb_admin_secret_id` | `enable_memory=true`일 때 기존 Vault Secret OCID |
| 선택 | `name`, `profile` | `oci-agent-launchpad`, `DEFAULT` |
| 선택 | `vcn_cidr`, `subnet_cidr` | `10.78.0.0/16`, `10.78.1.0/24`; 고객 네트워크와 중복 없이 지정 |
| 선택 | `vm_shape`, `vm_ocpus`, `vm_memory_gb` | `VM.Standard.E5.Flex`, 1 OCPU, 8GB |
| 선택 | `boot_volume_gb` | 50GB |
| 선택 | `enable_memory`, `adb_name`, `adb_version` | true, LPMEMORY, 26ai |
| 선택 | `adb_ecpus`, `adb_storage_gb` | 2 ECPU, 20GB; 자동 확장 끔 |
| 선택 | `bootstrap_packages` | Python 3.12과 pip; 준비된 커스텀 이미지는 `[]` 가능 |

Vault Secret은 ADB 관리자 암호 요구 조건을 만족해야 하며 관련 Vault/IAM 접근은 별도로 준비해야 합니다. 비밀 본문을 Terraform에서 읽는 data source는 사용하지 않습니다. 그래도 state·plan은 접근을 제한해 보관해야 합니다.

## 사용

Terraform 1.5 이상과 OCI 인증 설정, 대상 구획의 생성 권한이 필요합니다. VM·ADB 생성에는 사용 요금이 발생합니다.

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# 필수값과 조건부 필수값 수정
terraform init
terraform fmt -check
terraform validate
terraform plan -out=review.tfplan
# 생성 대상과 비용 구성 검토 후 실행
terraform apply review.tfplan
```

ADB 없이 실행하려면 `enable_memory=false`로 지정합니다. SSH만 지정 IP에 허용하고 앱 포트는 공개하지 않습니다. ADB TLS 접근은 생성한 VM의 IP로 제한됩니다. 이 구성은 공개 IP 기반 데모 프로파일이며 운영용 private endpoint/서브넷 프로파일은 아직 없습니다.

## 생성 이후와 기존 자원

이 템플릿만으로 앱이 실행되지는 않습니다. 앱 패키지 배포, GenAI IAM 정책, Agent Memory 스키마 초기화·실행 계정 설정, DevOps 파이프라인 및 Companion 등록은 별도 단계입니다. 현재 하드코딩된 예제 스크립트를 새 환경에서 그대로 실행하면 안 됩니다. 다음 작업은 이 단계들의 입력을 Terraform outputs와 릴리스 설정에 연결하는 것입니다.

기존 리소스는 별도 state에 import한 뒤 변경 없는 plan을 확인해야 합니다. 지금 템플릿을 apply하면 새 리소스가 생성됩니다. ADB에는 `prevent_destroy`가 있지만 리소스 블록 제거·state 관리 변경까지 막는 보장은 아닙니다. 기존 ADB에 대한 import나 apply는 이번 작업에서 수행하지 않습니다.

[OCI ADB 공급자 참조](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/database_autonomous_database.html)

## 검증 결과

2026-11-06: Terraform 1.13.5 / OCI provider 8.29.0으로 `fmt`, `validate` 성공. `terraform test`의 모의 공급자 테스트 3개(ADB 비활성화, 전체 공개 SSH 거부, 메모리 Secret 필수) 통과. 테스트에는 Terraform 1.7 이상이 필요합니다. 실제 OCI plan/apply·Resource Manager 실행은 아직 검증하지 않았습니다. 공급자 버전·체크섬은 `.terraform.lock.hcl`에 고정했습니다.
