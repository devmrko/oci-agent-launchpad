# 새 VM에서 패키지와 Agent Memory를 연결하기

고객별 VM을 구성하는 담당자가 같은 릴리스를 반복 설치하도록 만드는 선택형 첫 부팅 절차입니다. Terraform에는 패키지·Secret 식별자만 넣고, 새 VM이 Instance Principal로 앱용 DB 자격 증명을 받습니다. DB 관리자 암호를 VM 부팅 설정에 넣지 않습니다.

**현재 상태:** 2026-11-06 서울에서 새 Oracle Linux VM을 생성하고 Vault 앱용 자격 증명 수신, 검증된 0.4.1 패키지 설치, 실제 모델 요청, Oracle 메모리 저장·검색, VM 재부팅 후 복구를 확인했습니다. 검증 중 발견한 다운로드 응답 처리·코드 파일 권한 오류는 저장소와 새 VM의 부팅 스크립트를 수정해 복구했습니다. 수정본으로 또 다른 빈 VM을 처음부터 무개입 생성하는 재검증은 수행하지 않았습니다.

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

## 실제 검증과 수정한 문제

서울 `Joungmin.Ko`의 `oci-agent-launchpad-bootstrap-vm`은 E5 Flex 1 OCPU·8GB, 50GB 부트 볼륨입니다. 기존 예제 VM과 ADB를 유지하며 기존 ADB ACL에 새 VM의 `/32` 주소만 추가했습니다. 두 VM이 실행 중이므로 추가 VM·디스크 비용이 발생합니다. 후속 검증에서 신규 VM 전용 DevOps 파이프라인을 별도 workspace로 구성하고 Companion 화면에서 재배포 SUCCEEDED, 모니터링 UP / 0.4.1을 확인했습니다. 모니터링은 로컬 터널 8094로 전환했으며 기존 연결은 백업했습니다. [연결 검증과 다음 범위](../docs/companion-agent-platform-review.md)를 참고하세요.

처음 생성 404는 테넌시의 `INSTANCE_CREATE` 거부 조건이 `request.instanceOptions.areLegacyEndpointsDisabled != 'true'`였기 때문입니다. IMDSv2만 허용하도록 `are_legacy_imds_endpoints_disabled = true`를 명시하자 생성에 성공했습니다. 거부 정책을 변경하거나 사용자 권한을 확대하지 않았습니다. SDK 생성 스크립트에도 같은 설정을 반영했습니다.

첫 설치에서는 두 가지를 추가로 고쳤습니다. OCI 다운로드 응답의 파일 스트림은 `response.data.raw`로 읽어야 했습니다. 또한 부팅 서비스의 `UMask=0077`이 앱 코드에도 적용돼 실행 권한 오류가 발생했습니다. 코드 설치 구간만 `022`로 실행하고 이후 원래 마스크를 복구합니다. DB 설정·토큰·서비스 환경 파일은 계속 비공개입니다. 수정본을 SSH로 배치한 뒤 이미 다운로드한 패키지를 재사용해 설치를 완료했으며, 별도 수동 pip 설치는 하지 않았습니다.

확인한 결과:

- Python 배포 테스트 35개와 subtest 3개, Terraform 모의 공급자 4개 통과.
- 실제 앱 `UP / 0.4.1`, SELinux Enforcing 유지.
- 실제 OCI 모델의 규정 출처 확인, 승인 전 접수 금지, 승인 중복 방지, 추적 조회 통과.
- 대화를 통한 기억 저장과 새 세션 검색, 근거 ID, 원문 비노출 통과.
- VM 재부팅 후 `BOOTSTRAP_ALREADY_INITIALIZED`, 앱 자동 복구 확인.
- 재부팅 전후 SQLite·데모 토큰·메모리 설정·서비스 환경 파일 해시 일치. Oracle에 저장한 기억 재조회 통과.
- 기존 VM `0.4.1 / UP` 유지. Terraform 최종 plan은 `No changes`.

초기 관리자 작업인 ADB 스키마 생성·Vault 게시·기존 ADB ACL 갱신, 신규 VM의 DevOps 환경과 Companion 등록은 별도 단계입니다. 기존 계정의 과거 권한을 회수하는 마이그레이션과 운영용 인증·다중 VM 가용성까지 완료한 것은 아닙니다.

## 기존 VM의 부팅 설정 변경

OCI provider는 `metadata.user_data` 변경을 VM 교체로 처리합니다. 업무 데이터가 있는 VM을 부팅 코드 편집만으로 교체하지 않도록 이 필드의 변경 감지를 제외했습니다. 수정한 부팅 코드는 다음 새 VM 생성에 적용됩니다. 기존 VM의 cloud-init 본문은 업데이트되지 않으며, 일반 앱 갱신은 DevOps 릴리스로 수행합니다. 기존 VM의 부팅 도구를 수정해야 하면 관리자 패치를 별도로 검증·배치합니다. 이 생명주기 규칙은 이미지·사양 등 다른 변경의 교체 가능성까지 막지 않으므로 항상 plan을 검토합니다.
