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
