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

Companion에서 `빌드 → 실행 이력 → 저장하지 않은 빌드의 이력 → OCI DevOps 이력`으로 이동해 파이프라인을 선택합니다. 첫 실행 링크가 보이지 않으면 `명세 조회·수정 → 파라미터 수정·실행`으로 이동합니다. 소스 커밋을 고정하고 `빌드·테스트만`을 선택해 실행합니다. 현재 Registry 전달 단계가 없어 빌드 성공만으로 패키지 영구 저장이나 배포가 완료되지 않습니다.

## 현재 검증 범위

2026-11-06: 새 VM의 앱과 분리된 일반 사용자 작업 공간에서 Linux/Python 3.12 실제 빌드를 실행했습니다. 의존성 검사·패키지 import와 예제 테스트 14개가 통과했고 ZIP(앱 0.4.1 / Foundation 0.1.2) 및 release.json이 생성됐습니다. 기존 서비스 버전은 바꾸지 않았습니다. 로컬 배포 도구 회귀 테스트 44개와 하위 검사 3개가 통과했습니다.

Companion 첫 실행은 로그 미설정으로 거부됐습니다. 로그 활성화 후 브라우저 확장 UI가 자동화를 차단하여, 후속 관리형 빌드는 SDK로 시작했습니다. 이 기록은 Companion 버튼 성공이나 관리형 빌드 최종 성공을 의미하지 않습니다. 최종 결과는 [현재 상태](../docs/status.md)에 별도로 기록합니다.
