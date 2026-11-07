# 빌드 결과를 배포에 사용할 수 있도록 보관하기

관리형 빌드의 ZIP과 검증 메타데이터를 OCI Artifact Registry에 함께 보관합니다. Companion 없이 OCI API로도 실행되며, Companion은 같은 빌드 파이프라인의 실행·조회 화면을 제공합니다. 이 모듈 자체는 앱을 배포하지 않습니다.

## 구성과 사용

기존 프로젝트·빌드 파이프라인·Managed Build 단계 ID, 리전·홈 리전·구획, 고유한 `artifact_version`이 필요합니다. build_spec.yml의 출력 이름은 `launchpad-release`, `launchpad-release-metadata`여야 합니다. 저장 파일은 release.zip과 release.json입니다.

이 모듈은 불변 저장소, DevOps artifact 참조 2개, Deliver Artifacts 단계와 기존 정책의 보완을 관리합니다. 기존 SDK source-read 정책을 import하고 원래 이름·설명·태그·정책문을 `existing_policy_*`에 그대로 넣어 보존합니다. 같은 정책을 다른 Terraform 상태에서 동시에 관리하지 않습니다. import 이후 기존 prepare_build.py는 확장된 파이프라인/정책을 자동으로 수정하지 않고 거부하므로 초기 준비용으로만 사용합니다.

plan의 저장소·참조·전달 단계와 IAM 추가 내용을 검토한 뒤 apply합니다. 배포 승인이 필요한 환경에서는 여기서 자동 배포 단계를 연결하지 않습니다. `artifact_version`은 이번 실행 전에 아직 존재하지 않는 값으로 지정합니다. 성공한 버전을 재사용해 덮어쓰지 않습니다. 실패 후 일부 파일만 저장된 경우에도 새 버전으로 재실행합니다.

## 권한 범위

정확한 build pipeline OCID의 주체만 허용합니다. 기존 소스 읽기 권한을 유지하며 저장소 조회, generic artifact 생성·읽기·목록 조회, 구획 내 DevOps 자원의 읽기를 추가합니다. DevOps 읽기는 프로젝트 한 개로 제한되지 않지만 정확한 빌드 파이프라인 주체만 허용합니다. generic artifact DELETE/UPDATE는 허용하지 않습니다. Artifact Registry 권한은 구획 범위이며 **특정 저장소 한 개로 제한된 정책이라고 해석하면 안 됩니다.** 고객 환경에서 더 강한 경계가 필요하면 전용 빌드 산출물 구획으로 분리합니다.

## 성공 확인과 다운로드

빌드와 전달 단계 모두 SUCCEEDED인지 먼저 확인합니다. 이후 저장소 ID·버전·빌드 ID를 지정하여 저장소 루트에서 실행합니다.

```sh
python deploy/fetch_build_result.py --region <리전> --run-id <성공한 빌드 OCID> \
  --repository-id <이 모듈의 repository_id 출력> --version <artifact_version> \
  --output .run/managed-build-result
```

도구는 빌드 성공, metadata의 build_id 일치, ZIP·manifest·내부 파일 체크섬, 앱/Foundation 버전과 고정 의존성을 확인합니다. 실패한 빌드나 다른 빌드의 파일은 배포 출력으로 내보내지 않습니다. 조회 계정에는 해당 빌드와 아티팩트 읽기 권한이 필요합니다. 비밀값은 입력하지 않습니다. 체크섬은 디지털 서명이 아니며 임의 출처의 메타데이터를 신뢰하게 해 주지는 않습니다.

검증한 결과는 `verify_release.py`로 기존 [패키지 배포 모듈](../release/README.md)에 연결합니다. 앱 활성화·실패 복구·실제 모델/메모리 smoke는 별도 완료 조건입니다.

2026-11-07 저장소·전달 단계·정책 실제 apply(4 생성, 1 변경, 0 삭제)를 확인했습니다. 다운로드 도구와 패키지 검증 테스트 10개 통과. 후속 실행 `launchpad-050-deliver-readfix`에서 빌드와 전달 단계 모두 SUCCEEDED를 확인했습니다. 실제 Registry의 release.zip/release.json을 다운로드하여 빌드 ID·고정 소스·체크섬·내부 패키지 검증까지 통과했습니다. Terraform 후속 plan은 No changes였습니다.

근거: [Deliver Artifacts 단계](https://docs.oracle.com/en-us/iaas/Content/devops/using/add_deliverartifact.htm), [Artifact Registry 권한](https://docs.oracle.com/en-us/iaas/Content/artifacts/iam-policies-verb-resource-type-combinations.htm).
