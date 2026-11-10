# 명세부터 실행 기록까지 한 화면에서 확인하기

Companion의 **개발·실행 근거** 화면에서 출장비 앱 A·B 버전의 명세, 테스트 결과, ZIP 해시와 로컬 실행 기록을 함께 확인합니다. 전달받은 패키지가 어떤 요구와 검증 결과에 연결되는지 확인하는 용도입니다.

현재 화면은 검증한 파일을 내보낸 **스냅샷**입니다. 화면에서 OCI에 배포하거나 실행 중인 앱 상태를 조회하지 않습니다. 출장비 예제의 Langfuse 링크는 도구를 열며 개별 trace와 연결되지는 않습니다. 아래의 Hello Agent 연결 절차는 별도의 실제 배포·trace 기록을 가져옵니다. 각 기록의 한계를 화면에 표시합니다.

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

## 실제 OCI 배포와 Langfuse trace 연결하기

Hello Agent의 기존 [Companion Job 검증 기록](../../examples/hello-agent/verification/companion-job-2026-11-09.json)은 한 실행의 배포 ID·Job 완료·앱 버전·trace ID를 함께 보관합니다. 이 기록을 OCI 배포 조회와 Langfuse 관측 조회 결과에 대조하여 별도 카드로 가져올 수 있습니다. 새 배포나 모델 호출은 하지 않습니다.

1. 승인된 OCI 프로필에서 기록의 `delivery.deployment_id`를 `oci devops deployment get --deployment-id <ID> --region <리전>`으로 조회해 JSON 파일로 저장합니다. CLI의 `data` 래퍼를 유지합니다.
2. Langfuse 검증 VM에서 아래 수집기를 실행합니다. 기존 `.env`의 `LF_INIT_PUBLIC`·`LF_INIT_SECRET`을 사용하며 서버 자신의 loopback 주소에만 요청합니다. 출력에는 프로젝트·trace ID, 관측 종류, 입출력 존재 여부와 조회 시각만 포함됩니다. 키나 실제 입력·출력 본문은 포함하지 않습니다.

```sh
python3 collect_langfuse_evidence.py \
  --env-file /path/to/existing/.env \
  --trace-id <기록의_chat.trace_id> \
  --observed-at <기록의_observed_at_unix> > trace-snapshot.json
```

수집기 원본은 [scripts/collect_langfuse_evidence.py](../../scripts/collect_langfuse_evidence.py)입니다. 실행 기록 전후 10분 안에서 최대 100개 미만의 관측만 읽습니다. 프로젝트를 하나로 확인할 수 없거나 범위를 초과하면 실패합니다. 수집 결과 파일을 Launchpad 작업 컴퓨터로 가져온 뒤 실행합니다.

```sh
python3 -S scripts/export_cloud_evidence.py \
  --record examples/hello-agent/verification/companion-job-2026-11-09.json \
  --deployment .run/deployment-snapshot.json \
  --trace .run/trace-snapshot.json \
  --scope-file .run/companion-scope.json \
  --langfuse-url http://localhost:18080 \
  --append-to .run/companion-delivery-evidence.json \
  --output .run/companion-delivery-evidence-cloud.json
```

`--append-to`는 선택 사항입니다. 새 출력 파일을 Companion의 `companion.delivery-evidence` 설정으로 지정합니다. 위 A·B 기록에 추가하면 `entries: 3`입니다. 중복 항목이나 기존 출력 파일은 덮어쓰지 않습니다.

배포 ID·리전·구획, health/응답 버전, 응답/관측 trace ID, Langfuse 프로젝트가 일치해야 합니다. Job 완료와 업무 검사 PASS, AGENT·GENERATION·TOOL의 입력·출력 존재를 각각 확인합니다. 배포 성공만으로 업무 검증을 통과시키지 않습니다. 실패·누락·다른 실행 기록은 가져오기를 거부합니다.

카드에서 OCI 배포 상세와 해당 Langfuse trace를 열 수 있습니다. trace 링크는 [Langfuse 공식 상세 URL 형식](https://langfuse.com/docs/observability/features/url)을 사용하며 기존 로그인·프로젝트 접근 권한이 필요합니다. 공개 trace로 전환하지 않습니다. 수집은 [Observations API v2](https://langfuse.com/docs/api-and-data-platform/features/public-api)의 trace ID·시간 범위 조건을 사용합니다.

2026-11-10 기존 배포의 `SUCCEEDED`와 같은 trace의 세 관측을 실제로 다시 조회하고 화면 입력을 생성했습니다. 이는 과거 실행의 관측이 보관되어 있음을 확인한 것이며 현재 앱의 정상 동작을 재실행한 결과는 아닙니다. 이 과거 기록에는 명세·소스·이미지 해시의 연결이 없으므로 해당 부분은 **미연결**로 표시합니다. 현재 저장소의 명세를 과거 배포의 명세로 대신 표시하지 않습니다. 원본 JSON과 조회 스냅샷은 운영자가 제공한 자료이며 전자서명이나 독립적인 배포 승인 증명이 아닙니다.
