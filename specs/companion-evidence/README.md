# 명세부터 실행 기록까지 한 화면에서 확인하기

Companion의 **개발·실행 근거** 화면에서 출장비 앱 A·B 버전의 명세, 테스트 결과, ZIP 해시와 로컬 실행 기록을 함께 확인합니다. 전달받은 패키지가 어떤 요구와 검증 결과에 연결되는지 확인하는 용도입니다.

현재 화면은 검증한 파일을 내보낸 **스냅샷**입니다. OCI에 배포하거나 실행 중인 앱 상태를 조회하지 않습니다. Langfuse 링크는 도구를 열며, 이 예제의 개별 trace와 연결되지는 않습니다. 화면에도 이 한계를 표시합니다.

## 먼저 로컬 실행 기록 만들기

[패키징·실행·복구 실습](../local-release/README.md)을 완료합니다. Python 3.12 이상에서 저장소 루트를 기준으로 실행하세요.

```sh
mkdir -p .run
python3 -S scripts/local_release_demo.py --output .run/local-release
```

`LOCAL_RELEASE_PASS`와 `active_release: a`가 나오면 내보낼 준비가 되었습니다.

## Companion 범위와 모니터링 주소 연결하기

`.run/companion-scope.json`에 Companion에서 선택할 접속 범위를 작성합니다. 아래 값은 예시이며 실제 선택 값으로 바꿉니다. 비밀번호나 API 키는 넣지 않습니다. 이 파일은 저장소에 커밋하지 마세요.

```json
{
  "profile": "DEFAULT",
  "tenancy": "<테넌시 OCID>",
  "user": "<사용자 OCID>",
  "demo": false,
  "region": "ap-seoul-1",
  "compartment": "<구획 OCID>"
}
```

```sh
python3 -S scripts/export_companion_evidence.py .run/local-release \
  --scope-file .run/companion-scope.json \
  --langfuse-url http://localhost:18080 \
  --output .run/companion-delivery-evidence.json
```

브라우저가 다른 컴퓨터에 있다면 `--langfuse-url`에는 그 컴퓨터에서 접근 가능한 모니터링 주소를 사용합니다. 인증 정보를 포함한 URL은 거부합니다. 정상 결과는 `EXPORTED`, `entries: 2`, `live_cloud_queries: false`입니다. 기존 출력은 덮어쓰지 않으므로 갱신할 때는 새 파일 이름을 지정하세요.

## 화면 열기

[Companion 화면 설치 안내](../../integrations/companion/README.md)에 따라 별도 Companion 개발 체크아웃에 화면을 설치하고 JSON 경로를 설정합니다. 로그인한 뒤 `/delivery/evidence` 또는 왼쪽 메뉴 **개발·실행 근거**를 엽니다.

- 여섯 가지 접속 범위가 모두 일치해야 기록이 보입니다.
- A는 테스트 15개와 복구 후 선택 기록, B는 테스트 16개와 고의 장애 실습 기록을 표시합니다.
- 명세 원문은 각 ZIP에 들어 있는 내용입니다. 테스트 근거 해시는 JSON을 키 순서로 정규화한 내용의 SHA-256입니다.
- `OCI 미배포`, `이 릴리스와 미연결`은 오류가 아니라 현재 검증 범위입니다.
- 입력 파일이 없으면 빈 화면, 손상되었으면 안내 메시지가 표시됩니다. 파일 경로나 내부 예외는 노출하지 않습니다.

내보내기는 ZIP과 기록된 해시, 패키지 안의 파일과 테스트 근거를 대조합니다. 화면을 열 때 테스트를 재실행하거나 ZIP을 재검사하지 않습니다. 스냅샷은 서명된 증명이나 배포 승인이 아니므로 생성 시각과 원본 실행 기록을 함께 확인하세요.

[설계와 완료 조건](design.md)
