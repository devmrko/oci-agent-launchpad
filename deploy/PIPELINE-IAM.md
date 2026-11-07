# 배포 파이프라인을 기존 IAM 정책에 연결하기

운영자가 새 릴리스의 파이프라인 ID를 잘못 복사하거나 이전 배포 권한을 누락하지 않도록 Terraform 상태에서 연결 대상을 검증한다. Companion은 준비된 파이프라인을 실행하고, 이 도구는 그 전에 필요한 정책 입력과 계획 검사를 담당한다.

## 구현 계약

`prepare_pipeline_iam.py`는 정책 소유 workspace의 변수와 `terraform show -json` 상태, 새 릴리스의 상태를 받는다. 두 상태의 프로젝트·구획·VM이 같아야 하며 실제 배포 환경도 그 VM 하나를 선택해야 한다. 기존 정책 문장이 현재 입력으로 생성되는 문장과 정확히 일치해야 한다. 새 릴리스는 자체 정책을 소유하지 않는 재사용 경로여야 한다.

기존 변수는 보존하고 `additional_pipeline_ids`에 상태에서 확인한 정확한 ID만 추가한다. 새 출력 디렉터리에만 생성한다. 상태는 실시간 조회가 아니므로 생성 직전 갱신하고, 클라우드의 최종 차이는 저장한 Terraform 계획으로 확인한다. 정책 개수·문장 수 한도를 해결하거나 추가 권한을 임의로 확대하지 않는다.

계획 검사는 관리 리소스 생성·삭제·교체와 정책 외 변경을 거부한다. 대상 정책에서도 기존 속성은 유지하고 예상한 문장 목록만 허용한다. unknown 값·정책 외 drift·실패한 조건 검사도 거부한다. 파일 생성과 계획 검사 자체는 클라우드를 변경하지 않으며, 통과한 저장 계획의 적용은 별도 단계다.

완료 기준: 기존 권한 보존, 대상 불일치·오래된 입력 거부, 예상 외 Terraform 변경 거부 테스트, 기존 0.5.0 연결에 대해 실제 계획이 무변경임을 확인한다. 새 버전이 없는 상태에서 검증용 파이프라인을 중복 생성하지 않는다.

## 실행 순서

최초 정책은 기존 릴리스 workspace가 소유한다. 새 릴리스는 [준비 도구](PREPARE-RELEASE.md)와 [VM 등록](REGISTER-RELEASE.md)을 거친 뒤 `create_deployment_policy=false`로 별도 workspace에서 생성한다. Terraform 적용은 파이프라인을 생성할 뿐 앱 배포를 시작하지 않는다. 새 파이프라인 생성 실패를 무시하고 다음 단계로 진행하지 않는다.

아래 경로는 절대 경로로 지정한다. `owner-vars.json`은 기존 정책 소유자의 최신 입력 파일이며 기존 모든 `additional_pipeline_ids`를 포함해야 한다. 상태·계획 JSON에는 인프라 정보가 포함되므로 `.run` 같은 비공개 작업 경로에 보관하고 Git에 올리지 않는다.

```sh
TF_WORKSPACE='<정책 소유 workspace>' terraform -chdir=infra/terraform/release show -json > /absolute/work/owner-state.json
TF_WORKSPACE='<새 릴리스 workspace>' terraform -chdir=infra/terraform/release show -json > /absolute/work/release-state.json

python deploy/prepare_pipeline_iam.py prepare \
  --owner-vars /absolute/work/owner-vars.json \
  --owner-state /absolute/work/owner-state.json \
  --release-state /absolute/work/release-state.json \
  --output /absolute/work/iam-binding

TF_WORKSPACE='<정책 소유 workspace>' terraform -chdir=infra/terraform/release plan \
  -input=false -lock-timeout=30s \
  -var-file=/absolute/work/iam-binding/owner.tfvars.json \
  -out=/absolute/work/iam-binding/policy.tfplan
terraform -chdir=infra/terraform/release show -json /absolute/work/iam-binding/policy.tfplan > /absolute/work/iam-binding/plan.json

python deploy/prepare_pipeline_iam.py check-plan \
  --plan /absolute/work/iam-binding/plan.json \
  --binding /absolute/work/iam-binding/binding.json
```

`PLAN_VERIFIED` 후 실제 추가 사항이 있을 때 **그 저장 계획**을 정책 소유 workspace에서 적용한다. 다른 계획을 새로 만들거나 파일을 바꿨으면 다시 검사한다. Terraform 자체의 상태 잠금·오래된 계획 검사도 유지한다. 검사 결과는 서명이 아니며 관리자 작업 경로를 신뢰해야 한다.

```sh
TF_WORKSPACE='<정책 소유 workspace>' terraform -chdir=infra/terraform/release apply \
  -input=false /absolute/work/iam-binding/policy.tfplan
```

적용 성공 뒤 생성된 `owner.tfvars.json`을 이후 정책 소유 workspace의 입력으로 계속 사용한다. 예전 입력으로 되돌리면 추가 권한이 빠질 수 있다. 파일 생성·계획 검사 성공이 IAM 적용 성공을 뜻하지 않는다. 이후 Companion에서 성공 빌드와 새 배포 파이프라인을 연결해 실행하고 DevOps 결과와 앱 상태를 확인한다.

## 검증 결과와 한계

2026-11-07 IAM 도구 20개와 등록·준비 테스트를 합쳐 47개가 통과했다. 새 파이프라인 추가는 테스트 상태로 검증했고, 실제 서울 0.5.0 파이프라인은 이미 연결된 상태여서 `already_bound=true`였다. 생성한 입력의 실제 Terraform 계획은 `No changes`, 별도 검사는 `PLAN_VERIFIED`였다. 클라우드 자원을 추가하거나 IAM을 변경하지 않았다.

OCI provider 스키마에서 `ETag`, `lastUpdateETag`는 deprecated·computed 필드로 확인됐다. 실제 refresh에서 빈 값이 채워진 사례가 있어 정책 비교에서는 이 두 메타데이터 필드만 제외한다. 정책 문장·ID·구획·설명 등 다른 필드 변경은 거부한다. 일반 리소스 drift는 별도 검토 대상으로 남긴다.

[통합 파이프라인 실행 도구](PROVISION-PIPELINE.md)가 릴리스 생성 계획·적용과 IAM 연결 계획·적용을 순서대로 수행한다. 통합 명령의 실제 신규 권한 적용과 적용 후 무변경 계획까지 검증했다. Companion 화면의 앱 배포 실행과 그 이후 확인은 아직 남아 있으며 상세 범위는 통합 실행 문서에 기록한다. VM 등록·IAM·Terraform·Companion 사이에 분산 트랜잭션은 없다. 각 단계의 성공을 확인하고 실패한 단계부터 진행한다.
