# 고정 소스로 배포 패키지 만들기

개발 PC의 설치 상태에 의존하지 않고 Launchpad와 Foundation의 특정 커밋으로 Linux 배포 패키지를 만듭니다. Companion과 독립된 CLI이며 OCI Managed Build에서도 같은 명령을 실행하는 것이 목표입니다. 현재 OCI 빌드 파이프라인 연결은 미완료입니다.

## 준비

- Linux x86_64와 Python 3.12, Git, venv가 필요합니다.
- 승인된 두 Git 저장소의 체크아웃과 정확한 커밋을 준비합니다. 사설 저장소 인증은 실행 환경에서 제공하며 패키지에 포함하지 않습니다.
- Foundation 소스의 버전이 예제의 고정 의존성과 같아야 합니다. 현재 예제는 0.1.2를 요구합니다.
- 패키지 다운로드를 위한 네트워크가 필요합니다. 런타임 의존성은 requirements-memory.lock의 정확한 버전을 사용합니다. 빌드 도구의 하위 의존성까지 완전히 재현 가능한 공급망을 검증한 것은 아닙니다.

## 실행

환경 변수에 각자의 저장소 경로와 커밋을 넣은 뒤 실행합니다. 출력 디렉터리는 아직 없어야 합니다.

```bash
python3.12 deploy/build_release.py \
  --foundation "$FOUNDATION_SOURCE" \
  --foundation-revision "$FOUNDATION_COMMIT" \
  --launchpad . \
  --launchpad-revision "$LAUNCHPAD_COMMIT" \
  --build-id "$BUILD_ID" \
  --output .run/build-result
```

성공하면 `release.zip`과 `release.json`이 만들어집니다. JSON에는 소스 커밋, 앱/Foundation 버전, 빌드 ID, 패키지·manifest 해시와 검증 결과가 있습니다. 테스트나 의존성 검증 실패 시 최종 출력 디렉터리는 생성되지 않습니다. 비밀값·VM 주소·메모리 계정은 입력이나 산출물에 넣지 않습니다.

`release.zip`은 기존 설치 도구가 사용하는 형식입니다. 별도 `release.json`은 추적용 메타데이터이며 서명이나 배포 승인 자체를 대신하지 않습니다. 승인된 manifest 전달과 Companion의 릴리스 연결은 후속 구현입니다.

소스 번들만 필요하면 `deploy/package_sources.py`에 동일한 저장소/revision 인자와 `--output .run/sources.tgz`를 지정합니다. 미커밋 변경을 포함하지 않고 허용된 소스 경로만 내보냅니다. 같은 입력 커밋은 같은 소스 번들 해시를 생성합니다. 임의 파일 안의 모든 비밀 문자열을 탐지하는 보안 스캐너는 아니므로 저장소에 비밀값을 커밋하지 않아야 합니다.

OCI 연결 시 [공식 Build Specification](https://docs.oracle.com/en-us/iaas/Content/devops/using/build_specs.htm)의 Managed Build 단계와 BINARY output artifact를 사용합니다. 두 소스 접근·Python 실행 환경·산출물 전달을 실제 OCI에서 확인한 후 연결 완료로 표시합니다.

## OCI 입력 스냅샷과 빌드 단계

개인 Git 토큰을 빌드 환경에 전달하는 대신, 허용한 두 소스 커밋으로 만든 `sources.tgz`를 같은 OCI 프로젝트의 전용 Code Repository에 게시하는 경로를 검증 중입니다. 이 저장소는 빌드 입력 스냅샷이며 GitHub 정본을 대신하지 않습니다. 저장소에는 다음 파일만 게시합니다.

- `sources.tgz`, `source.sha256` (소스 번들 전체 SHA-256)
- `deploy/build_release.py`, `deploy/package_sources.py`, `deploy/package_release.py`
- 이 프로젝트의 `deploy/build_spec.yml`을 저장소 루트의 `build_spec.yml`로 복사한 파일

CLI에서도 `--source-archive sources.tgz --source-sha256 <검증한 해시>`를 저장소/revision 인자 대신 사용할 수 있습니다. 출처를 신뢰하는 번들만 실행합니다. SHA-256은 전달 무결성을 확인하며 소스의 신뢰나 서명을 대신하지 않습니다.

[변수 예제](build-config.example.json)를 복사해 준비된 OCI 프로젝트·Code Repository·구획을 지정한 뒤 실행합니다. `prepare_build.py`는 해당 프로젝트의 전용 빌드 파이프라인·단계·파이프라인 주체에 한정한 소스 읽기 정책을 만듭니다. 기존 이름의 구성이 다르면 덮어쓰지 않고 실패합니다. IAM 홈 리전의 정책 생성 권한이 필요합니다. SDK 기반 도구이며 아직 Terraform 자원으로 통합하지 않았습니다.

```bash
python deploy/prepare_build.py --config .run/build-config.json --output .run/build-pipeline.json
```

**실행 전 프로젝트의 DevOps 서비스 로그를 활성화해야 합니다.** 실제 첫 시도에서 로그가 없어 OCI가 HTTP 409 IncorrectState로 빌드를 거절했습니다. 해당 프로젝트의 로그를 30일 보존으로 활성화했습니다. 로그·저장소·빌드 러너는 OCI 사용 요금 대상일 수 있습니다. 이 도구는 로그 자원을 생성하지 않습니다.

`runner`를 생략하면 OCI 기본 러너를 사용합니다. 선택값으로 `"runner": {"ocpus": 2, "memory_in_gbs": 8}`을 지정할 수 있습니다. 기존 파이프라인의 러너·브랜치가 입력과 다르면 자동 변경하지 않습니다. 실제 서울 검증에서는 기본 러너 확보가 두 번 실패하여 같은 2 OCPU·8GB의 명시적 할당을 시험했습니다. 리전 용량 부족이라고 단정할 증거는 아직 없습니다.

Companion에서 `빌드 → 실행 이력 → 저장하지 않은 빌드의 이력 → OCI DevOps 이력`으로 이동해 파이프라인을 선택합니다. 첫 실행 링크가 보이지 않으면 `명세 조회·수정 → 파라미터 수정·실행`으로 이동합니다. 소스 커밋을 고정하고 `빌드·테스트만`을 선택해 실행합니다. Registry 전달 단계 구성과 다운로드는 [빌드 산출물 보관](../infra/terraform/build-delivery/README.md)을 따릅니다. 빌드 성공만으로 앱 배포가 완료되지는 않습니다.

## 현재 검증 범위

2026-11-06: 새 VM의 앱과 분리된 일반 사용자 작업 공간에서 Linux/Python 3.12 실제 빌드를 실행했습니다. 의존성 검사·패키지 import와 예제 테스트 14개가 통과했고 ZIP(앱 0.4.1 / Foundation 0.1.2) 및 release.json이 생성됐습니다. 기존 서비스 버전은 바꾸지 않았습니다. 로컬 배포 도구 회귀 테스트 45개와 하위 검사 3개가 통과했습니다.

Companion 첫 실행은 로그 미설정으로 거부됐습니다. 로그 활성화 후 브라우저 확장 UI가 자동화를 차단하여, 후속 관리형 빌드는 SDK로 시작했습니다. 이 기록은 Companion 버튼 성공이나 관리형 빌드 최종 성공을 의미하지 않습니다. 최종 결과는 [현재 상태](../docs/status.md)에 별도로 기록합니다.

최종 OCI 결과: 기본 러너 두 번과 명시적 2 OCPU·8GB 한 번 모두 `Unable to get Build Runner, please try again.`으로 실패했습니다. 빌드 명령 이전의 GET_BUILD_RUNNER 실패이며 Registry 전달이나 배포는 수행되지 않았습니다. 서비스 할당 상태를 확인한 뒤 고정 커밋으로 다시 실행할 수 있습니다. 같은 실패를 반복해 실행 성공으로 간주하지 않습니다.

## 검증된 산출물을 배포 입력으로 연결하기

Linux 빌드 결과를 받은 뒤 저장소 루트에서 실행합니다. `base-vars.json`에는 배포 대상 리전·구획·프로젝트·VM 등 기존 Terraform 변수가 있어야 합니다. 기존 릴리스 상태를 재사용하지 않고 새 workspace를 사용하세요.

```bash
python deploy/verify_release.py --result .run/build-result \
  --base-vars .run/base-vars.json --alias memory-0.4.2 \
  --output .run/release-042.tfvars.json
```

이 도구는 ZIP·manifest·파일 목록·개별 해시·wheel의 실제 앱/Foundation 버전·고정 의존성을 대조하고, 검증된 파일 경로와 해시를 배포 변수에 넣습니다. `release.json`은 선택적 Terraform 아티팩트로 ZIP 옆에 보관됩니다. 해시와 메타데이터는 서명 또는 소스 신뢰를 대신하지 않습니다. 빌드가 테스트를 실행했다는 진술의 독립적인 증명도 아닙니다.

다음은 [VM 설치 관리자 준비와 Terraform 배포](../infra/terraform/release/README.md)를 따릅니다. 현재 관리자 manifest 등록과 산출물 전달은 별도 단계이며 Companion에서의 자동 완주 경로는 아직 미완성입니다.


## 0.5.0 관측 연결 빌드 입력 (2026-11-07)

앱 커밋 `f06ee98c4a5985eaafaa68445151840c95908260`, Foundation 커밋 `d207f52281552a551457733bebc0ee62036b36e3`을 소스 번들로 고정했다. SHA-256은 `63f01c19ade50fc03e11d7faef81e0f65b834112b3e34d3be8ab3a65459a572b`이며 OCI 입력 저장소 커밋 `cb9ae51a126953ef254e5bffeb18dc5d03a47998`에 게시했다. 런타임 Langfuse 키는 포함하지 않는다.

Companion의 Edge 탭에서 빌드 메뉴 이동을 시도했지만 다른 확장 UI 때문에 자동화가 차단됐다. 따라서 이번 빌드 시작은 OCI SDK로 수행했고 Companion 버튼 성공으로 간주하지 않는다. 실행 이름은 `launchpad-050-telemetry`, ID는 `ocid1.devopsbuildrun.oc1.ap-seoul-1.amaaaaaavsea7yiazzgqd6lub73rtwobwvq7sgiakoi3vc4da7pggwobqpta`다. 2026-11-07 04:22 UTC경 확인 상태는 IN_PROGRESS / GET_BUILD_RUNNER이며 소스 빌드·Linux 테스트·release.zip 생성 성공은 아직 확인하지 않았다. 이 기록은 이후 성공이나 실패로 자동 갱신되지 않는다.

[상시 관측 연결의 설정과 남은 작업](SERVICE-DESK-LANGFUSE.md#상시-연결의-현재-차이와-다음-적용-순서)을 함께 확인한다. 빌드 성공만으로 사설 VCN 연결, 비밀 파일 배치, 앱 활성화가 완료되지는 않는다.


### 첫 0.5.0 빌드 결과와 수정 재시도

첫 실행은 러너 확보·Python 설치까지 성공했으나 pip 패키지 다운로드에서 프록시 DNS 오류로 FAILED였다. 패키지 버전 부재로 단정하지 않는다. `build_release.py`에 선택값 `LAUNCHPAD_PIP_NETWORK=direct`를 추가했다. 기본값은 기존 설정 상속이며 direct 모드는 pip 명령에만 프록시·PIP 환경변수/설정 파일을 제외하고 공식 PyPI HTTPS 인덱스를 지정한다. TLS 검증은 유지한다. 프록시가 필수인 고객 환경에서는 이 값을 지정하지 않는다. 관련 빌드 테스트 7개 통과. 설정 파일 제외 방식의 근거는 [pip 설정 문서](https://pip.pypa.io/en/stable/topics/configuration/)다.

수정 도구 커밋 `9f01ac3`, OCI 입력 커밋 `e3fecd85329492aad051660c782eb09d4c576b25`로 `launchpad-050-direct-pip`을 시작했다. 앱 소스 번들의 커밋·해시는 그대로다. 실행 ID는 `ocid1.devopsbuildrun.oc1.ap-seoul-1.amaaaaaavsea7yiaovlamzarcfhgj5zsnca5jc2ucchopyzsxda6hxdqbrlq`. 재시도는 접수 확인 단계이며 성공 결과는 별도 확인이 필요하다.


### Linux 빌드 성공 및 산출물 전달 권한 보완 (2026-11-07)

직접 PyPI 연결 재시도는 의존성 설치에 성공했으나 모니터링 테스트 2개에서 SQLite 정렬 구문 오류가 발생했다. NULLS LAST 대신 NULL 여부와 시간·ID를 정렬하는 호환 구문으로 수정했다. 앱 커밋 `8fce79b2d0a416f15d3605a31d729e7cb9d641e4`, OCI 입력 커밋 `38b98eb8ba9f60acde9e6012679290904a9d11a6`의 관리형 빌드 `launchpad-050-portable`은 실제 Linux 빌드·테스트·패키지 생성 및 출력 보관 단계까지 SUCCEEDED였다. 소스 번들 SHA-256은 `8e4455d372b9b80f15d2ab7f329b1071baa28c00a38d59355ab00ec7693fe122`이다.

후속 `launchpad-050-deliver`는 빌드에 성공했지만 Artifact Registry 전달에서 DevOps artifact 참조 조회 권한 오류로 실패했다. 기존 프로젝트 조건이 포함된 개별 리소스 읽기 대신, 정확한 빌드 파이프라인 주체에만 구획 내 `read devops-family`를 부여했다. Terraform 적용은 0 생성·1 변경·0 삭제다. 테넌시 전체 manage 권한을 추가하지 않았다. 저장소가 비어 있음을 확인한 후 같은 고정 소스로 `launchpad-050-deliver-readfix`를 시작했다. 이 재시도는 빌드와 전달 단계 모두 SUCCEEDED였고 실제 다운로드 검증까지 통과했다. 실행 ID는 `ocid1.devopsbuildrun.oc1.ap-seoul-1.amaaaaaavsea7yiahwreauygqn3ssxrymxv2rd43qkhuxrtpdwdvx6pf7aca`다. 패키지 SHA-256은 `329179a5f71d4e2541587db438819be162bc42495848ffcfd730f7cd02ec10f4`, manifest SHA-256은 `691d3d05f7d8dcf261e7974b2a5752e9d8200df177d1b85a3a18a5f58bfeeffc`다. 후속 OCI DevOps 배포도 SUCCEEDED였고 실제 0.5.0 health·모델·메모리·Langfuse 연결 검증을 통과했다. [상시 연결 결과](SERVICE-DESK-LANGFUSE.md#050-서비스에-상시-연결-적용-2026-11-07)를 참고한다.

새 릴리스의 Terraform 입력과 VM 허용 설정을 함께 준비하려면 [릴리스 준비 도구](PREPARE-RELEASE.md)를 사용한다. 빌드 ID·소스 커밋을 고정하고 기존 복구 별칭을 보존하며, 파일 준비와 실제 배포 완료를 구분한다.
