# 새 VM에서 패키지와 Agent Memory를 연결하기

고객별 VM을 구성하는 담당자가 같은 릴리스를 반복 설치하도록 만드는 선택형 첫 부팅 절차입니다. Terraform에는 패키지·Secret 식별자만 넣고, 새 VM이 Instance Principal로 앱용 DB 자격 증명을 받습니다. DB 관리자 암호를 VM 부팅 설정에 넣지 않습니다.

**현재 상태:** 코드와 로컬 경계 테스트는 통과했습니다. 2026-11-06 서울 실제 적용에서는 네트워크 생성 후 VM 생성이 OCI `404 NotAuthorizedOrNotFound`로 실패했습니다. 새 VM 첫 실행·메모리 통신·재부팅 후 유지까지 검증한 구성은 아닙니다. 기존 0.4.1 VM의 패키지 배포 검증과 구분해야 합니다.

## 동작과 준비 조건

1. 운영자가 ADB의 별도 소유자·실행 계정을 초기화합니다. `initialize_memory.py`는 stdin으로 관리자 자격 증명을 받고, 마지막에 실행 계정으로 실제 로그인과 저장소 조회를 검증합니다. 기존 계정의 암호를 자동 변경하지 않습니다.
2. `publish_runtime_secret.py`에 실행 계정 설정만 stdin으로 전달합니다. ADMIN/SYS/SYSTEM/스키마 소유자 계정과 허용 목록 밖의 필드를 거부합니다. 같은 이름·내용은 재사용하며, 내용이 다르면 명시적 회전 절차를 요구합니다.
3. Terraform이 새 VM과 VM ID로 제한한 IAM 정책을 만듭니다. cloud-init이 Python 3.12 및 부팅용 OCI SDK 2.188.0을 설치합니다. 따라서 첫 부팅에는 패키지 저장소로의 네트워크 접근이 필요합니다.
4. VM이 지정 Vault Secret과 Artifact Registry 패키지를 받고 전체 ZIP·manifest·각 파일의 SHA-256을 검증합니다. 앱 의존성은 패키지 안의 wheel로 오프라인 설치합니다.
5. 앱 사용자·서비스·개별 데모 토큰을 준비하고 `127.0.0.1:8092/health`의 버전을 확인합니다. 성공 마커가 있으면 이후 부팅은 설치와 비밀값 재작성을 건너뜁니다. 일반 버전 갱신은 DevOps 릴리스 경로를 이용합니다.

Vault와 AES 키, 게시한 앱 패키지, 초기화한 Agent Memory 저장소가 먼저 있어야 합니다. `enable_memory=false`는 새 ADB를 만들지 않는다는 뜻이며 기존 ADB 메모리 사용은 가능합니다. 기존 ADB ACL에는 새 VM 공인 IP를 추가해야 합니다. 기존 허용 IP를 덮어쓰거나 전체 인터넷에 열지 않습니다. 새 ADB 생성 옵션은 스키마 초기화와 Secret 게시를 대신하지 않습니다.

## 필수·선택 입력

[기본 Terraform 입력](../infra/terraform/README.md)에 다음 선택 객체를 추가합니다. `runtime_bootstrap`을 생략하면 첫 실행 기능을 사용하지 않습니다. 객체를 지정할 때 아래 필드는 모두 필수입니다.

| 필드 | 의미 |
|---|---|
| `artifact_id`, `artifact_sha256` | 같은 구획에 게시된 ZIP의 OCID와 실제 SHA-256 |
| `manifest_sha256` | ZIP 내부 manifest의 SHA-256 |
| `runtime_secret_id` | 같은 구획의 앱 실행 계정 설정 Secret OCID |
| `release_alias`, `app_version` | 안전한 릴리스 별칭과 설치된 앱의 버전 |
| `model_region`, `chat_model`, `embedding_model` | 모델 실행 위치와 ID. Secret의 임베딩 설정과 일치해야 함 |

`home_region`은 IAM 홈 리전이며 기본값은 `us-ashburn-1`입니다. 테넌시에 맞게 변경합니다. 실제 비밀값은 tfvars·plan·이미지·Git에 넣지 않습니다. Secret 설정 필드는 `dsn`, `user`, `password`, `schema_owner`, `store_id`, `compartment`가 필수이며 임베딩·namespace 필드는 선택입니다. 이 bootstrap 경로에서는 `embedding_region`, `embedding_model`도 반드시 일치하도록 채웁니다.

```hcl
enable_memory = false
runtime_bootstrap = {
  artifact_id       = "<generic artifact OCID>"
  artifact_sha256   = "<64자리 SHA-256>"
  manifest_sha256   = "<64자리 SHA-256>"
  runtime_secret_id = "<앱용 Vault secret OCID>"
  release_alias     = "memory-0.4.1"
  app_version       = "0.4.1"
  model_region      = "us-ashburn-1"
  chat_model        = "google.gemini-2.5-flash-lite"
  embedding_model   = "cohere.embed-v4.0"
}
```

위 모델 값은 기존 합성 예제의 값이며 고객 데이터의 리전 요건에 맞는지 별도로 확인합니다. ZIP은 해당 OS·아키텍처·Python 3.12용 wheel이어야 합니다.

## 첫 성공 확인과 재개

일반 `terraform plan`과 `apply` 절차를 사용합니다. 기존 자원은 별도 state를 유지하며 이 구성에 자동 편입하지 않습니다. 생성이 완료되면 새 IP의 ADB 접근을 허용하고 다음을 확인합니다.

```sh
sudo systemctl status launchpad-bootstrap launchpad-demo
sudo journalctl -u launchpad-bootstrap --no-pager
curl -fsS http://127.0.0.1:8092/health
```

첫 실행 완료 로그는 `BOOTSTRAP_READY version=0.4.1`입니다. 단계 로그의 `identity`, `runtime-secret`, `artifact`, `install`, `start-service`로 중단 위치를 구분합니다. 비밀값이 포함될 수 있는 SDK 예외 본문은 출력하지 않습니다. 실패 시 30초 후 재시도하므로 IAM 반영과 ACL 준비 후 다시 진행할 수 있습니다.

health 성공만으로 메모리를 검증했다고 보지 않습니다. 예제의 `smoke_memory_chat.py`로 저장·다른 세션 검색을 확인하고, `smoke_memory_api.py save` 후 VM을 재부팅해 `verify`로 보존 여부를 확인해야 합니다. 토큰은 `/var/lib/launchpad/.run/demo-accounts.json`에 있으며 출력하지 않습니다. 이후 DevOps VM 환경과 Companion 연결을 별도로 구성해야 합니다.

2026-11-06 적용에서는 새 VCN·게이트웨이·라우팅·보안 목록·서브넷이 Terraform state에 남아 있습니다. VM과 bootstrap IAM 정책은 생성되지 않았습니다. 이미지 조회·서브넷 조회는 성공했지만 Terraform과 SDK 모두 생성 404를 반환했습니다. 기존 서브넷과 이전 Oracle Linux 9.8 이미지 비교도 같은 결과였습니다. 권한 문제인지 다른 자원 접근 문제인지는 확정하지 못했습니다. 실패한 plan을 다시 적용하지 말고 현재 state에서 새 plan을 만든 뒤 남은 생성 대상을 확인합니다. ADB ACL은 변경하지 않았습니다.

실제 수행한 검증: Python 33개와 3개 subtest, Terraform 모의 공급자 4개 통과. 기존 ADB 실행 계정 로그인·저장소 조회와 앱용 Vault Secret 생성은 성공했습니다. 기존 계정에 이미 부여됐던 권한을 회수하는 마이그레이션은 포함하지 않습니다. 새 VM 생성 실패로 부팅 통합 검증은 남아 있습니다.
