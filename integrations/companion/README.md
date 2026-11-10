# Companion에 사용자 앱 운영·개발 근거 화면 설치하기

이 확장은 사용자 앱 등록·배포·상태·로그·복구 화면과 개발 근거 화면을 추가합니다. 앱 운영은 [사용자 앱 운영 안내](../../specs/user-app-platform/README.md)의 관리 서버와 접속 범위 파일을 먼저 준비하세요. 개발 근거 화면은 Launchpad에서 검증한 릴리스 기록을 Companion의 접속 범위별로 보여 줍니다. [사용 목적과 기록 생성 방법](../../specs/companion-evidence/README.md)을 먼저 확인하세요.

Companion은 별도 저장소입니다. 이 폴더는 화면과 테스트를 복사하는 소스 확장이며, Companion 본체에 병합된 배포판은 아닙니다. `0.1.0-SNAPSHOT` 개발 소스에서 확인했습니다. 설치기는 기존 `CatalogPages.java`와 `layout.html`을 수정하고 같은 이름의 확장 파일을 덮어쓰므로, 별도 개발 체크아웃에서 실행하고 변경 사항을 검토하세요.

Launchpad 저장소 루트에서 설치합니다.

```sh
python3 integrations/companion/install.py /absolute/path/to/oci-companion
```

대상 Companion 폴더에서 Java 21과 기존 Maven 설정을 사용해 검증하고 실행합니다.

```sh
./mvnw -Dtest=UserAppPagesTest,DeliveryEvidenceTest,DeliveryEvidenceWebTest package
java -jar target/oci-companion-0.1.0-SNAPSHOT.jar \
  --companion.delivery-evidence=/absolute/path/to/companion-delivery-evidence.json
```

기존 프로필과 접속 설정을 사용하는 작업 디렉터리에서 실행하세요. 기본 입력 경로는 `.data/delivery-evidence.json`입니다. 이 확장은 로그인이나 네트워크 접근 설정을 변경하지 않습니다. 원격 접속은 기존 Companion 설정을 사용합니다.

설치 후 `/delivery/evidence`에서 로그인, 접속 범위 일치, A·B 기록과 명세 원문을 확인합니다. Java 테스트는 범위 격리, 위험한 링크 거부, 손상 파일 처리, 로그인 요구와 HTML 이스케이프를 검사합니다. Launchpad의 Python 테스트는 실제 로컬 릴리스 생성과 내보내기, 해시 불일치와 출력 덮어쓰기 거부를 검사합니다.

화면 조회와 스냅샷 내보내기는 클라우드 API를 호출하지 않습니다. 별도 수집 단계에서 OCI 배포와 Langfuse 관측을 읽고, 기존 Hello Agent 검증 기록의 배포 ID·버전·trace ID와 대조할 수 있습니다. [실제 배포 기록 연결 방법](../../specs/companion-evidence/README.md#실제-oci-배포와-langfuse-trace-연결하기)을 참고하세요. 명세·소스·이미지 해시까지 묶는 연결은 후속 작업입니다.
