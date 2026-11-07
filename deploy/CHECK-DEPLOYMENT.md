# 배포 후 앱·메모리·관측 기록을 함께 확인하기

운영자가 배포 상태만 보고 성공으로 판단하지 않도록 service-desk 예제의 실제 기능과 Langfuse 기록을 검사한다. 이 검사는 합성 데모용이다. 모델 호출 비용이 발생하고 합성 세션·메모리 1개 이상이 생성되며 자동 삭제하지 않는다.

## 구현 계약

`examples/service-desk/scripts/check_deployment.py`는 기존 check_runtime의 인증·버전·실제 OCI 모델·세션 간 메모리 검사를 재사용한다. 별도 합성 채팅과 메모리 검색의 request ID로 Langfuse 관측을 대조한다. 채팅의 3개 span과 메모리의 2개 span, 채팅 입출력 존재, 메모리 본문 제외를 확인한다.

Langfuse v2 조회는 고정 시간 범위와 cursor로 전체 페이지를 읽는다. 빈 페이지에 cursor가 있으면 계속 조회한다. 순환 cursor·페이지 한도 초과·잘못된 응답은 실패다. 수집 지연은 제한된 횟수만 재조회하며 인증 오류를 정상으로 취급하지 않는다. stdout에는 결과·검사명·trace ID만 출력하고 토큰·본문·서버 오류 응답은 출력하지 않는다.

근거: [Langfuse 공식 API](https://api.reference.langfuse.com/), [OpenAPI 명세](https://cloud.langfuse.com/generated/api/openapi.yml). 환경의 실제 버전과의 호환성은 별도 실측한다.

## 실행

`check_deployment.py`와 `check_runtime.py`를 같은 디렉터리에 둔다. 실행 환경에는 예제의 기존 의존성인 httpx가 필요하다. 앱 및 Langfuse에 연결할 수 있는 VM에서 실행하거나 로컬 터널을 사용한다. 합성 데이터용 계정과 Langfuse 프로젝트를 지정하고, 해당 데모에서는 채팅 `capture_content=true`를 명시적으로 설정해야 입출력 검사를 통과한다. 검증 도구는 이 설정을 자동 변경하지 않는다.

자격 증명은 명령행 인자·로그에 넣지 않고 stdin으로 공급한다. 입력 형식은 다음과 같다. 실제 파일을 사용할 경우 소유자만 읽도록 제한한다.

```json
{
  "token": "<합성 데모 계정의 기존 토큰>",
  "langfuse": {
    "url": "http://<비공개 Langfuse 주소>:8080",
    "public_key": "<프로젝트 공개 키>",
    "secret_key": "<프로젝트 비밀 키>"
  }
}
```

```sh
python examples/service-desk/scripts/check_deployment.py \
  --base-url http://127.0.0.1:8092 \
  --expected-version 0.5.0 \
  --credentials-stdin < /protected/check-credentials.json
```

자격 증명을 기존 런타임 설정에서 읽는 경우 메모리에서 JSON을 만들고 자식 프로세스 stdin으로 전달해도 된다. 이 도구는 특정 환경 파일 위치나 첫 번째 계정을 자동 선택하지 않는다. 대상 계정 선택은 운영자가 관리하는 호출 측 책임이다.

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--base-url` | 필수 | 앱 HTTP 주소 |
| `--expected-version` | 필수 | 기대하는 앱 버전 |
| `--credentials-stdin` | 필수 | stdin JSON 사용 명시 |
| `--attempts` | 25 | 관측 수집 지연 재조회 횟수, 1~60 |
| `--interval` | 2초 | 재조회 간격, 0~10 |
| `--max-pages` | 20 | 한 조회에서 읽을 최대 페이지 수, 1~100 |

성공은 JSON `result=PASS`, 프로세스 종료 코드 0이다. 실패는 `result=FAIL`, 종료 코드 1이다. HTTP 상태 오류는 상태 코드만 출력한다. `Observation page limit reached`는 결과 불완전이며, 한도를 조정하거나 별도 합성 프로젝트에서 다시 검사한다. 페이지를 덜 읽은 상태로 통과 처리하지 않는다.

기본 관측 조회에서는 최대 100개씩 읽고 `meta.cursor`가 없을 때 끝낸다. 응답이 비어 있더라도 cursor가 있으면 다음 페이지를 읽는다. 특정 테스트 요청만 request ID로 남기며 다른 사용자의 본문은 결과 파일에 출력하지 않는다. 수집 시점 이후의 새로운 관측을 무기한 검증하는 도구는 아니다.

## 확인한 범위

2026-11-07 로컬 테스트 13개 통과: 빈 페이지 이후 cursor, 반복 cursor, 페이지 한도, 인증 오류, 본문 누락·메모리 본문 노출·오류 span 거부, 자격 증명 오류 출력 방지, HTTP 요청부터 관측 대조까지의 연결을 검사했다.

실제 서울 VM의 새 릴리스에서 stdin으로 기존 자격 증명을 전달한 CLI 실행이 PASS였다. 앱 버전 0.5.0, 인증·실제 OCI 모델·세션 간 Oracle Agent Memory 검사, Langfuse 관측 5개·채팅 입출력·메모리 본문 제외를 확인했다. 근거 파일은 비공개 `.run/oci-launchpad/check-deployment-reusable.json`이다. 실제 고트래픽 다중 페이지 검증은 하지 않았고, 페이지 전환은 HTTP 테스트 대역으로 검증했다.

이 도구는 service-desk 합성 시나리오의 배포 확인용이며 범용 에이전트 평가나 지속 모니터링을 대체하지 않는다. 앱이 보고하는 버전만으로 실행 파일 경로까지 증명하지 않으므로 동일 버전 재배포 시 systemd ExecStart 같은 실행 경로도 별도 확인한다. 임시 검증 스크립트 대신 이 저장소의 버전 관리된 도구를 다음 배포에서 사용한다.
