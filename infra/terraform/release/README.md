# 에이전트 패키지를 OCI에서 설치·배포하기

이미 실행 중인 에이전트 VM에 새 버전을 배포하려는 운영자를 위한 Terraform 구성입니다. 로컬의 승인된 ZIP 패키지를 OCI Artifact Registry에 올리고, DevOps가 VM으로 전달하여 검증·설치·활성화하게 합니다. 새 버전 상태 확인이 실패하면 기존 릴리스 전환 도구가 직전 버전을 복구합니다.

서울 예제에서 0.4.1을 사전 설치하지 않은 상태로 이 경로를 실행했고, DevOps `SUCCEEDED`와 앱 `UP · 0.4.1`을 확인했습니다. 기존 Oracle Agent Memory 기록 조회와 새 채팅 기억 저장·조회도 통과했습니다.

## 만드는 것과 필요한 것

이 구성은 불변 패키지 저장소, 패키지 업로드, DevOps 배포 환경·파이프라인·명세·패키지 참조·단계, 전용 IAM 정책을 관리합니다(기본 8개 리소스, 메타데이터 포함 시 9개). 기존 정책을 사용하는 선택 경로에서는 새 IAM 정책을 만들지 않습니다. 기존 VM·ADB·네트워크는 생성하거나 수정하지 않습니다. 배포 환경은 입력한 VM 한 개만 참조합니다.

필수 준비물:

- 기존 DevOps 프로젝트와 Oracle Linux VM, Python 3.12 및 Run Command 플러그인.
- 정상 실행 중인 systemd 앱과 기존 릴리스. 최초 서비스·ADB schema·비밀값 설정은 [기존 배포 안내](../../../deploy/README.md)를 참고하세요.
- 대상 구획의 Artifact Registry·DevOps 생성과 IAM 정책 생성 권한이 있는 OCI 프로파일.
- 대상 VM과 같은 OS/CPU/Python용 wheel 패키지. 예제는 Linux x86_64/Python 3.12입니다.

## 1. 오프라인 패키지 준비

앱과 Foundation의 승인된 wheel을 `wheelhouse/`에 넣습니다. 예제 앱은 저장소 루트에서 `python -m pip wheel --no-deps examples/service-desk -w wheelhouse`로 빌드할 수 있습니다. Foundation 0.1.2 wheel도 같은 디렉터리에 넣으세요.

Linux x86_64/Python 3.12 환경에서 실행합니다. 아래 작업은 현재 앱에 설치하지 않고 배포 파일만 준비합니다.

```sh
cp examples/service-desk/requirements-memory.lock requirements.txt
printf '\ndevmrko-python-foundation==0.1.2\nlaunchpad-service-desk==0.4.2\n' >> requirements.txt
python3.12 -m pip download --only-binary=:all: --find-links wheelhouse \
  -r requirements.txt -d wheelhouse
python3.12 deploy/package_release.py --wheels wheelhouse \
  --requirements requirements.txt --output release.zip
```

마지막 명령은 `bundle_sha256`과 `manifest_sha256`을 출력합니다. ZIP은 wheel·고정 requirements·manifest만 포함합니다. OCI 키·ADB 비밀번호·환경 파일은 넣지 않습니다. Terraform을 실행하는 호스트로 ZIP을 가져옵니다.

## 2. VM에 설치 도구 준비

관리자 bootstrap 작업입니다. 앱의 새 릴리스를 미리 설치하지 않습니다. [릴리스 설정 예제](../../../deploy/release.example.json)를 복사해 기존 별칭을 유지하고 다음 값을 추가합니다.

```json
{
  "staging_root": "/var/ocarun_staging/launchpad",
  "releases": {
    "memory-0.4.2": {
      "directory": "memory-0.4.2",
      "version": "0.4.2",
      "manifest_sha256": "<패키지 생성 시 출력된 manifest SHA-256>"
    }
  }
}
```

위 조각은 전체 설정이 아닙니다. `service`, `release_root`, `port`와 기존 `releases` 항목을 합친 JSON을 사용하세요. `activate_release.py`, `install_release.py`, `bootstrap_release.py`를 같은 디렉터리에 전송한 뒤 VM에서 실행합니다.

```sh
sudo python3 bootstrap_release.py --config package-deployment.json
```

bootstrap은 설치 도구를 바꾸기 전에 staging 상위 경로의 root 소유·쓰기 제한, leaf의 소유권·쓰기 제한을 검사하고 `runuser`로 실제 `ocarun` 계정의 상위 경로 통과 및 leaf 쓰기를 확인합니다. 다른 계정 소유 경로, symlink, 공유 쓰기 경로는 거부합니다. root 소유의 비어 있지 않은 staging은 자동 소유권 변경하지 않습니다. 기존 상위 경로의 권한을 자동으로 넓히지 않으며 오류에 나온 정확한 경로를 관리자가 확인해야 합니다.

이미 준비된 VM에서는 변경 없이 검사할 수 있습니다. `bootstrap_release.py`와 `activate_release.py`를 같은 관리자 작업 디렉터리에 두고 실행하세요.

```sh
sudo python3 bootstrap_release.py --config /etc/launchpad-deployment.json --check
```

성공 메시지는 root 신뢰와 `ocarun` 경로 접근 검사 통과를 뜻합니다. Artifact Registry 다운로드·Run Command 전체 실행·SELinux 서비스 도메인 접근·앱 준비 상태까지 보장하지 않습니다.

bootstrap은 root 소유 설치 도구·설정과 `ocarun`의 별칭별 제한된 sudo 명령을 준비합니다. 패키지 자체는 이후 DevOps가 가져옵니다. `staging_root`는 Terraform 값과 일치해야 합니다.

## 3. Terraform 적용

이 디렉터리에서 실행합니다. 상태 파일은 다음 배포와 복구에 필요하므로 보관합니다.

```sh
cp terraform.tfvars.example local.tfvars
# local.tfvars의 OCID, 파일 경로와 두 체크섬을 채웁니다.
terraform init
terraform plan -var-file=local.tfvars -out=release.tfplan
terraform apply release.tfplan
```

| 필드 | 필수 여부 | 의미 |
|---|---|---|
| `region`, `home_region` | 필수 | 배포 리전과 테넌시 IAM 홈 리전 |
| `compartment_id`, `project_id`, `instance_id` | 필수 | 같은 구획의 기존 프로젝트·VM |
| `release_alias`, `app_version` | 필수 | VM 별칭과 설치 후 기대 버전 |
| `bundle_path`, `bundle_sha256`, `manifest_sha256` | 필수 | 로컬 ZIP과 검증값 |
| `release_metadata_path` | 선택, null | 검증된 release.json을 ZIP 옆에 저장 |
| `create_deployment_policy` | 선택, true | 기존 정책 소유자가 권한을 부여하면 false |
| `additional_pipeline_ids` | 선택, 빈 목록 | 이 정책 소유자가 추가 허용할 정확한 배포 파이프라인 OCID |
| `profile` | 선택, `DEFAULT` | 로컬 OCI 프로파일 |
| `name` | 선택, `oci-agent-launchpad` | 리소스 이름 접두사 |
| `staging_root` | 선택, `/var/ocarun_staging/launchpad` | VM의 전달 경로 |
| `post_deploy_check_command` | 선택, null | 사전 설치한 `/usr/local/sbin/` 검증 래퍼 경로 |
| `post_deploy_check_timeout_seconds` | 선택, 300 | 후속 검사 제한 시간(30~600초) |

Terraform은 파일 SHA-256과 실제 업로드 SHA-256을 비교합니다. 패키지와 저장소는 삭제 방지 설정이 있습니다. **이 상태는 한 불변 릴리스를 관리합니다.** 새 버전은 별도 Terraform workspace/state로 구성하고 이전 상태·리소스를 유지하세요. 같은 버전의 ZIP을 바꿔 덮어쓰지 않습니다.

## 4. 배포 실행과 확인

Companion에서 해당 리전·구획의 **배포 → 준비된 파이프라인 실행·복구**를 열고 새 파이프라인을 선택합니다. 대상 확인 후 실행합니다. Terraform 자체는 배포를 시작하지 않습니다.

DevOps는 ZIP을 전달하고 설치 도구는 root 설정에 고정된 manifest와 모든 파일 체크섬을 확인합니다. 검증한 파일로 새 가상환경을 만들고 인터넷 없이 설치한 뒤 의존성과 앱 버전을 확인합니다. 기존 서비스는 설치가 끝날 때까지 계속 실행하며, 활성화 단계에서는 짧은 재시작이 발생합니다.

`SUCCEEDED`와 `/health`의 기대 버전·`UP`을 확인하세요. [메모리 검증 스크립트](../../../examples/service-desk/scripts/smoke_memory_chat.py)는 기본 0.4.2를 확인하며 다른 버전은 `EXPECTED_VERSION` 환경변수로 지정할 수 있습니다. 이전 버전으로 돌아가는 방법은 [릴리스 복구](../../../deploy/RELEASES.md)를 참고하세요.

## 검증과 구현 범위

- 로컬 배포 테스트 23개 및 하위 검사 3개, 예제 앱 14개, Companion 109개 통과.
- Terraform mock 테스트 4개: 불변 저장소, 체크섬 오류, 명령 삽입 별칭, 다른 구획 차단.
- 실제 Terraform apply 및 후속 plan의 `No changes` 확인.
- 실제 Registry → DevOps → VM 신규 설치, 기존 기억 조회, 새 기억 저장·조회, 동일 설치 재사용 확인.

OCI provider 8.29.0은 업로드 리소스의 `content`를 해시로, 인라인 명세를 디코딩된 문자열로 읽어 오는 차이가 있습니다. 이 두 표현의 변경 감지는 제외하되 실제 아티팩트 SHA-256과 명세 의미를 postcondition으로 비교하므로 불일치는 실패합니다. 기존 환경 data source에서 VM 선택 정보가 null로 반환되는 경우를 피하기 위해 배포 환경은 이 구성에서 직접 생성합니다.

VM 전체 초기화·ADB 사용자/비밀값 배치, 다중 VM 무중단 배포, 앱 데이터 schema 역변환은 포함하지 않습니다. VM에는 설치 관리자 준비가 필요합니다. 버전별 저장소·패키지와 클라우드 리소스는 사용량에 따른 비용이 발생합니다.

근거: [OCI 배포 명세](https://docs.oracle.com/en-us/iaas/Content/devops/using/deployment_specs.htm), [Artifact Registry 개요](https://docs.oracle.com/en-us/iaas/Content/artifacts/overview.htm), [권한별 리소스 작업](https://docs.oracle.com/en-us/iaas/Content/artifacts/iam-policies-verb-resource-type-combinations.htm).

## 정책 개수 한도가 있는 계정

새 릴리스에서 `create_deployment_policy=false`를 사용하고, 기존 정책을 소유한 workspace의 `additional_pipeline_ids`에 새 파이프라인 OCID를 추가합니다. 새 파이프라인 ID는 해당 릴리스의 `pipeline_id` 출력입니다. 정책 소유 workspace의 입력 파일에 추가 값을 지속해서 보관해야 다음 적용에서 권한이 사라지지 않습니다.

[IAM 연결 도구](../../../deploy/PIPELINE-IAM.md)는 기존 상태와 변수의 일치를 확인하고 추가 입력 및 Terraform 계획을 검사합니다.

기존 정책의 VM과 같은 대상에만 이 재사용 경로를 사용하세요. 다른 VM은 해당 VM의 명령 실행·아티팩트 읽기 권한도 별도로 필요합니다. 기존 상태의 단일 정책 주소는 `moved` 블록으로 `[0]`에 이동하며 삭제·재생성하지 않습니다. 계획에서 기존 권한 유지와 정확한 추가 파이프라인 범위를 확인한 뒤 정책 소유 상태를 적용하고 새 릴리스를 실행합니다. `false`만 설정하면 배포 권한이 자동으로 생기지 않습니다.

2026-11-06 서울 검증에서 테넌시 정책 500개 한도로 새 정책 생성이 거부됐고 이 경로를 적용했습니다. Terraform mock 검사 7개와 기존 정책의 6개 명시적 추가 권한을 확인했습니다.

후속 기능 검사를 연결할 때는 [검증 래퍼 계약과 준비 상태](../../../deploy/CHECK-DEPLOYMENT.md)를 먼저 확인하세요. 실패하면 배포는 실패로 표시되지만 이미 활성화한 앱의 자동 롤백을 의미하지 않습니다.
