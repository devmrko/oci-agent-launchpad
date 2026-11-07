# 검증된 빌드로 새 릴리스 입력 준비하기

운영자가 빌드 결과를 Terraform과 VM 설치 설정에 따로 옮기지 않도록 준비 도구를 제공한다. Companion에는 Launchpad 파일 형식을 넣지 않으며, 준비가 끝난 OCI 배포 파이프라인은 Companion의 일반 빌드·배포 연결로 실행한다.

## 구현 계약

입력은 신뢰하는 빌드 결과 디렉터리, 예상 빌드 ID·두 소스 커밋, 대상 VM의 기존 배포 설정, Terraform 기본 변수다. 출력에는 검증한 패키지 사본, Terraform 변수, 기존 복구 버전을 보존한 VM 설정, 출처 및 설정 해시 기록이 들어간다. 새 출력 디렉터리에만 생성하고 완료 표시는 모든 검증과 파일 생성 뒤 마지막에 쓴다. 실패한 출력에는 완료 표시가 없다.

패키지·버전·체크섬·빌드 ID·소스 커밋 불일치, 같은 별칭에 다른 manifest 등록, 기존 디렉터리 충돌, staging 경로 불일치, 예상 밖 설정 키를 거부한다. 기존 파일을 덮어쓰거나 클라우드·VM·IAM을 변경하지 않는다. 비밀 파일은 입력하지 않는다.

완료 기준은 정상 패키지에서 일관된 출력 생성, 기존 별칭 보존, 위 거부 조건 검사, 실제 0.5.0 패키지로 생성한 출력과 현재 배포 설정의 일치다. VM 등록·Terraform 적용·IAM 추가·배포 실행은 별도 단계이며 준비 완료가 배포 완료는 아니다.

## 실행

먼저 [빌드 결과 다운로드](../infra/terraform/build-delivery/README.md)로 성공한 실행의 release.zip과 release.json을 가져온다. `base-vars.json`은 배포 대상용 Terraform 변수이며 공유 IAM 정책 소유자의 입력을 넣지 않는다. `current-deployment.json`은 **그 대상 VM**의 `/etc/launchpad-deployment.json`을 관리자 권한으로 읽은 최신 사본이어야 한다. 준비 도구는 이 파일이 어느 VM에서 왔는지 자체적으로 인증하지 않는다.

저장소 루트에서 실행한다. Python 3.11 이상이 필요하다.

```sh
python deploy/prepare_release.py \
  --result .run/managed-build-result \
  --base-vars .run/base-vars.json \
  --deployment-config .run/current-deployment.json \
  --expected-build-id '<OCI에서 확인한 성공 빌드 OCID>' \
  --expected-launchpad-commit '<고정된 앱 소스의 40자리 commit>' \
  --expected-foundation-commit '<고정된 Foundation 소스의 40자리 commit>' \
  --output .run/prepared-release
```

`--alias`는 선택값이다. 생략하면 앱 버전과 패키지 해시 앞 12자리로 생성한다. 별칭을 지정하면 기존 동일 별칭은 directory·version·manifest가 전부 같을 때만 허용한다. 이는 재준비 허용이며 같은 이름의 다른 패키지로 교체하는 기능이 아니다.

| 출력 | 역할 |
|---|---|
| `result/release.zip`, `result/release.json` | 사본을 다시 검증한 배포 패키지·출처 |
| `release.tfvars.json` | 패키지 경로·해시·버전·배포 대상 |
| `deployment.json` | 기존 복구 별칭을 보존한 VM 허용 릴리스 설정 |
| `preparation.json` | 준비 완료 표시, 입력 설정·출력 설정 해시, 출처, 남은 작업 |

`preparation.json`의 READY는 **파일 준비 완료**만 뜻한다. 복사 중 오류가 나면 부분 출력 폴더는 검사할 수 있게 남기고 READY 파일을 쓰지 않는다. 같은 출력 폴더로 다시 실행하면 거부한다. 출력 폴더에는 제한된 권한을 사용하며 Terraform이 절대 파일 경로를 참조하므로 이동하지 않는다. 예상 빌드 ID·커밋은 신뢰한 빌드 요청에서 가져온다. 체크섬과 이 기록은 전자서명이 아니다.

## 준비 이후

[VM 설치 관리자와 Terraform 배포](../infra/terraform/release/README.md)를 따른다. 새 릴리스는 새 workspace를 사용한다. 기존 별칭 재준비 결과(`existing_alias_reused=true`)를 새 릴리스인 것처럼 적용하지 않는다. 이미 배포한 상태는 기존 workspace·파일 경로를 유지하고 차이를 검토한다.

VM 등록 전에 원격 설정이 준비 당시와 같은지 `previous_vm_config_sha256`과 대조한다. 달라졌으면 최신 설정으로 새 출력 폴더에 다시 준비한다. 이 대조와 등록은 아직 원자적으로 묶이지 않았으므로 등록 작업은 한 운영자만 수행한다. VM 등록은 기존 bootstrap 도구를 쓰며 환경변수·메모리 비밀 파일·서비스 데이터는 건드리지 않는다. 기존 정책을 재사용하는 경우 새 pipeline ID를 정책 소유 상태에 추가해야 한다. 마지막 배포 실행은 Companion의 성공 빌드 → 배포 연결을 사용한다.

## 검증 결과

2026-11-07 준비·패키지·다운로드 관련 테스트 22개 통과. 실제 관리형 빌드의 0.5.0 패키지로 생성한 VM 설정은 현재 VM 설정과 일치했고, Terraform 배포값도 패키지 사본 경로를 제외하고 현재 입력과 일치했다. 기존 0.4.1·0.4.2·0.5.0 별칭을 보존했다. 이 검증에서는 클라우드·VM 설정을 변경하지 않았다.

아직 자동화하지 않은 부분: VM 설정 최신성 검사와 등록의 단일 작업화, Terraform 적용·정책 소유 상태 갱신, 새 파이프라인 생성부터 Companion 배포까지의 전체 실행. Companion과의 공통 계약에는 이 앱의 manifest 형식을 추가하지 않는다.
