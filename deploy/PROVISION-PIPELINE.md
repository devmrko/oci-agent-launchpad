# 릴리스 파이프라인 생성과 IAM 연결을 함께 실행하기

운영자는 검증한 준비 결과를 지정하여 파이프라인 생성 계획을 확인하고, 실행 모드에서 생성과 기존 IAM 정책 연결을 순서대로 수행할 수 있다. 앱 배포는 이후 Companion에서 실행한다. VM 허용 목록 등록은 먼저 완료해야 한다.

## 구현 계약

`provision_pipeline.py`는 준비 결과의 SHA256과 패키지를 다시 검증하고 기존 release Terraform 모듈을 실행한다. 기본 모드는 계획만 생성한다. `--execute`가 있으면 검사한 저장 계획을 적용하고 실제 release 상태로 IAM 입력을 생성하여 정책 계획 검사·적용까지 진행한다. 새 의존성은 추가하지 않는다.

릴리스 계획은 기존 release 모듈의 8개 자원에 대한 생성 또는 무변경만 허용한다. 수정·삭제·교체·예상 밖 자원·IAM 생성은 거부한다. 이미 등록된 별칭을 재사용한 준비 결과로 새 자원을 만들지 않는다. 신규 자원에 대한 업로드 후 조건은 apply까지 unknown일 수 있으므로 계획 시 명시적 실패를 거부하고 적용 시 Terraform 조건 검사를 유지한다.

IAM 단계는 기존 추가 전용 검사 도구를 사용한다. 실패 시 생성한 자원을 자동 삭제하지 않는다. `progress.json`과 단계 로그를 남기며 IAM 단계만 다시 실행하는 `--iam-only` 경로를 제공한다. 재실행에는 새 출력 폴더를 쓰고, 기존 release workspace는 그대로 사용한다. IAM 적용이 성공했지만 결과 기록이 실패한 경우 최신 정책 입력·상태를 확인하고 재개해야 한다.

완료 기준은 단계 순서·실패 전파·위험 계획 거부 테스트, 실제 OCI에서 신규 파이프라인 계획 검증, 기존 파이프라인의 IAM 단계 무변경 검증이다. 실제 신규 자원 생성·전체 앱 배포는 별도 검증 범위로 기록한다.

## 준비와 실행

Python 3.11 이상, 초기화된 `infra/terraform/release` Terraform 디렉터리, OCI 인증 프로파일, 기존 정책 소유 workspace가 필요하다. [릴리스 준비](PREPARE-RELEASE.md)의 `create_deployment_policy`는 반드시 false여야 한다. 새 버전에는 새 release workspace를 만들고 기존 workspace를 재사용하지 않는다. 이 도구는 workspace 생성과 Terraform init을 대신하지 않는다.

1. 검증한 패키지로 준비 결과를 생성한다.
2. [VM 허용 목록 등록](REGISTER-RELEASE.md)을 완료한다. 계획만 확인할 때는 VM 등록을 뒤로 미룰 수 있다.
3. 새 release workspace를 생성한다. 정책 소유 workspace와 달라야 한다.
4. 아래 명령으로 계획을 확인한다. receipt 해시는 신뢰한 원본 `preparation.json`에서 계산한다.

```sh
python deploy/provision_pipeline.py \
  --prepared /absolute/work/prepared-release \
  --receipt-sha256 '<preparation.json SHA256>' \
  --release-workspace release-051 \
  --owner-workspace bootstrap-vm \
  --owner-vars /absolute/work/current-owner.tfvars.json \
  --output /absolute/work/provision-plan-051 \
  --terraform /absolute/path/to/terraform \
  --module /absolute/repository/infra/terraform/release
```

기본 모드는 `RELEASE_PLAN_VERIFIED`에서 종료한다. 이때 신규 pipeline ID는 아직 없으므로 IAM 계획도 아직 생성하지 않는다. 실행할 때는 **새 output 경로**와 `--execute`를 지정한다. 실행 모드도 새 계획을 만들고 검증한 뒤 그 저장 계획을 적용한다. 기존 dry-run 파일을 승인 증표로 재사용하는 방식은 아니다.

실행 성공의 마지막 상태는 `INFRASTRUCTURE_APPLIED`다. 이것은 Terraform과 IAM 적용 성공이며 앱 설치·배포 성공이 아니다. `output/iam/owner.tfvars.json`을 다음 정책 관리 작업의 입력으로 유지하고, Companion에서 성공 빌드와 새 파이프라인을 연결해 앱 배포를 진행한다. IAM 전파와 VM Run Command 준비 상태는 실제 배포에서 확인해야 한다.

## 실패 후 재개

`progress.json`에는 마지막 상태와 `failed_stage`가 남는다. Terraform 오류 세부 정보는 비공개 `terraform.log`, 검토할 계획은 `release.plan.json` 또는 `iam.plan.json`에서 확인한다. 전체 state JSON은 로그에 반복 출력하지 않는다. 실행 폴더는 0700이며 계획·로그를 Git에 올리지 않는다.

- **릴리스 적용 전/중 실패:** 해당 workspace 상태와 로그를 확인한다. 새 output으로 일반 실행을 다시 하면 남은 생성만 허용하고, 수정·교체 계획은 거부한다. 기존 상태를 삭제하지 않는다.
- **릴리스 생성 후 IAM 실패:** 같은 release workspace와 새 output을 지정하고 `--iam-only`로 IAM 계획만 다시 확인한다. 적용까지 수행하려면 `--iam-only --execute`를 사용한다. 실제 상태의 프로젝트·VM·별칭·버전·manifest를 다시 검사한다.
- **IAM 적용 후 상태 기록 실패:** 클라우드 정책과 Terraform 상태를 먼저 대조한다. 이미 추가된 권한을 반영한 owner-vars를 사용한다. 오래된 입력은 기존 권한 보존 검사에서 거부될 수 있다.

workspace 선택은 프로세스별 `TF_WORKSPACE`로 지정한다. `TF_CLI_ARGS*`와 `TF_VAR_*`는 자식 프로세스에서 제거하여 숨은 destroy/변수 옵션이 끼어들지 않게 한다. Terraform 실행 파일·모듈·프로파일·관리자 작업 경로는 신뢰한 것을 사용해야 한다. 패키지를 포함한 입력은 실행 중 다른 프로세스가 수정하지 않아야 한다. Terraform 자체 잠금·저장 계획의 오래된 상태 검사도 유지한다.

## 검증 범위

2026-11-07 통합 도구·IAM·등록·준비 관련 테스트 62개가 통과했다. 위험 계획 차단, 기본 모드의 적용 금지, 실행 단계 순서, IAM 실패 전파와 재개, 패키지 변조, 환경변수 격리, 로그 출력 범위를 검사했다.

실제 OCI 조회를 사용한 새 `provision-plan-050` workspace의 계획은 `RELEASE_PLAN_VERIFIED`로 통과했다. 기존 `bootstrap-050`의 IAM-only 경로는 `IAM_PLAN_VERIFIED`로 통과했다. 이후 기본 workspace 선택은 `bootstrap-050`으로 복원했다. 이 계획 검증 단계에서는 실제 자원·권한을 생성하지 않았다. 이후 실행 결과는 아래와 같다.

`--execute`의 전체 순서 테스트에 이어 같은 날 실제 서울 환경에서 적용했다. 검증된 0.5.0 패키지를 새 별칭 `memory-0.5.0-329179a5f71d`로 등록했고, VM 등록은 `REGISTERED` 및 앱 재시작 없음으로 종료됐다. release workspace `provision-plan-050`에서 8개 자원을 생성하고, 정책 소유 workspace `bootstrap-vm`의 기존 정책 1개만 수정했다. 삭제된 자원은 없으며 최종 상태는 `INFRASTRUCTURE_APPLIED`였다.

기존 0.4.2·0.5.0 파이프라인 권한을 보존한 새 owner-vars를 현재 정책 입력에도 반영했고 이전 사본을 보관했다. 적용 후 두 workspace의 실제 Terraform plan은 모두 상세 종료 코드 0(무변경)이었다. Companion의 실제 `OciBuildHandoff` 코드로 성공 빌드와 새 파이프라인의 패키지 1개 일치를 확인했고, 다른 0.4.2 파이프라인은 거부됐다.

이 검증은 동일한 0.5.0 패키지의 새 배포 경로 검증이며 앱 기능 버전을 올린 것은 아니다. Companion 화면에서 `launchpad-050-deliver-readfix` 성공 빌드의 **이 빌드로 배포 준비**를 선택하고, 새 파이프라인의 파일 1개 SHA256·크기 및 대상 VM 일치 확인 후 **확인한 배포 실행**을 눌렀다. 실행 이름은 `companion-1845de09-8c6b-4700-9ce2-45ae7a357b43`이다. 화면에서 ACCEPTED를 확인했고, 이후 새로고침이 Edge 확장 프로그램에 차단되어 같은 실행의 최종 `SUCCEEDED`는 OCI API로 확인했다. 최종 성공 화면 스크린샷은 확보하지 못했다.

VM의 systemd ExecStart가 `/opt/launchpad/releases/memory-0.5.0-329179a5f71d/venv/bin/python`으로 바뀌었고 새 프로세스가 `UP · 0.5.0`으로 응답했다. 기존 릴리스 디렉터리와 복구 별칭은 보존했다.

새 프로세스에서 합성 데이터로 인증된 capabilities, 실제 OCI 모델 호출·버전별 trace, Oracle Agent Memory의 세션 간 기억 저장·조회가 모두 PASS였다. 비공개 VCN/LB 경로의 Langfuse API에서 해당 요청의 관측 기록 5개를 확인했다. 채팅 입력·출력은 기록됐고 메모리 검색 본문은 input/output에서 제외됐다. 이 검증은 해당 합성 요청의 결과이며 모든 업무 시나리오·장애 복구·운영 규모를 보장하지 않는다.

실행 근거는 비공개 `.run/oci-launchpad/provision-execute-050`의 progress.json, Terraform 로그, after-release.log, after-iam.log, `.run/oci-launchpad/deployment-run-050-integrated.json`, `validation-050-integrated.json` 및 Companion 로컬 검증 결과다. 준비·계획 파일과 상태에는 운영 정보가 있어 공개 문서에 복사하지 않는다.

배포 후 반복 검증은 [앱·메모리·Langfuse 통합 확인](CHECK-DEPLOYMENT.md)의 버전 관리된 CLI를 사용한다. 이 도구는 배포 실행과 독립적이므로 Companion 배포 완료 후 운영 검사로 연결할 수 있다. 현재 Companion이 자동 실행하는 기능은 아니다.
