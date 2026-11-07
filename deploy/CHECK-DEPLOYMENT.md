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

## 파이프라인 후속 검사 연결 계약

release Terraform의 선택 입력 `post_deploy_check_command`로 VM에 사전 설치한 관리자 검증 래퍼를 지정한다. 값은 `/usr/local/sbin/` 아래 실행 파일의 절대 경로만 받으며 인라인 shell·인자·비밀값을 받지 않는다. 배포 명세는 설치·활성화 다음에 `sudo -n <경로> <릴리스 별칭>`을 실행한다. 래퍼는 root 소유 설정에서 별칭에 해당하는 기대 버전·합성 계정·Langfuse 연결을 찾아 위 CLI를 호출해야 한다.

기본값 null이면 후속 검사는 생략되어 기존 명세를 유지한다. `post_deploy_check_timeout_seconds` 기본값은 300초다. 검사 실패/시간 초과는 DevOps 배포 실패로 처리되지만 이미 활성화된 앱을 자동 롤백하지 않는다. 기존 활성화 단계의 health 실패 롤백과 별개다. 원인을 확인한 뒤 검사를 재실행하거나 이전 파이프라인으로 복구한다.

래퍼 설치 및 ocarun의 정확한 명령·별칭별 sudoers 허용이 선행되어야 한다. 이 Terraform 옵션 자체는 VM 파일이나 sudoers를 설치하지 않는다. 새 릴리스 workspace에서만 설정하며 기존 불변 배포 명세를 변경하지 않는다. Companion에는 명령 이름·앱 계정·Langfuse 비밀값을 넣지 않는다.

새 릴리스의 기본 변수에 다음 값을 추가하면 준비 도구가 검증한 후 Terraform 변수로 전달한다.

```json
{
  "post_deploy_check_command": "/usr/local/sbin/launchpad-check",
  "post_deploy_check_timeout_seconds": 300
}
```

`launchpad-check`는 아래 관리자 래퍼로 구현했고 실제 VM에 설치해 ocarun 실행까지 검증했다. 기존 불변 파이프라인에는 옵션을 소급 활성화하지 않았다. 새 릴리스의 명세에서 이 옵션을 사용한다. VM 등록 도구의 입력 검증 모듈도 새 옵션을 아는 동일 버전으로 배포해야 한다. 미지원 구버전은 알 수 없는 설정 키로 거부한다.

2026-11-07 후속 검사 연결의 Terraform mock 테스트 11개, 준비·등록·통합 실행·IAM 관련 Python 테스트 67개가 통과했다. 현재 실제 release workspace의 기본 옵션 계획은 종료 코드 0, `No changes`였다. 후속 검사 활성화 경로는 명세 생성과 입력 전달까지 검증했으며 실제 DevOps 실행 검증은 아직 하지 않았다.

## VM 관리자 래퍼 설계

`run_deployment_check.py`는 root 전용이며 `/etc/launchpad-check.json`의 허용 별칭만 받는다. 기대 버전·포트·실행 파일은 기존 `/etc/launchpad-deployment.json`에서 읽는다. 검사를 시작하기 전에 같은 배포 잠금을 잡고 systemd의 실제 ExecStart가 선택한 릴리스의 Python인지 확인한다. 다른 버전을 검사하거나 검사 중 배포가 전환되는 것을 막는다.

검증 설정과 자격 증명 파일은 root 소유·비소유자 쓰기 금지 경로이며 파일 권한은 0600이어야 한다. 검증 Python과 스크립트도 root 제어 경로여야 한다. 자식 프로세스는 제한된 환경변수와 stdin 자격 증명으로 실행하고, stderr나 원본 실패 응답을 출력하지 않는다. 실패·시간 초과·잘못된 결과는 종료 코드 1로 처리한다.

별도 `/etc/sudoers.d/launchpad-check`는 정확한 `/usr/local/sbin/launchpad-check <별칭>`만 ocarun에게 허용한다. 기존 설치·활성화 sudoers는 건드리지 않는다. 설정에 등록되지 않은 별칭과 명령행 URL·비밀 파일 경로 변경을 허용하지 않는다. 새 릴리스마다 이 검사 허용 목록도 갱신해야 하며, 이 단계에서는 기존 배포 파이프라인을 변경하지 않는다.

### 관리자 래퍼의 설정과 검증 결과

`/etc/launchpad-check.json` 예시(실제 파일은 root:root 0600):

```json
{
  "allowed_releases": ["memory-0.5.0-329179a5f71d"],
  "credentials_file": "/etc/launchpad-check-credentials.json",
  "timeout_seconds": 240
}
```

credentials_file은 앞서 설명한 stdin JSON 형식이며 root:root 0600으로 준비한다. 기존 데모 계정 중 `subject=demo-user`를 명시적으로 선택해 연결했고 토큰은 출력하지 않았다. 자격 증명을 회전하면 이 파일도 갱신해야 한다. 검증 프로세스의 최대 시간은 240초이며 Terraform 후속 단계의 300초보다 짧게 둔다.

실제 VM에는 `/usr/local/lib/launchpad-checks`에 검증 CLI·런타임 검사·관리자 래퍼 및 공통 검증 모듈을 설치했다. `/usr/local/sbin/launchpad-check`는 `/usr/bin/python3.12 -E -s`로 관리자 래퍼를 호출한다. 자식 검사도 사용자 site와 Python 환경변수를 무시하며 신뢰한 스크립트 디렉터리의 check_runtime만 불러온다.

관리자는 `run_deployment_check.py --sudoers`로 정확한 허용 명령 목록을 생성하고 `visudo -cf`로 검사한 뒤 별도 sudoers 파일에 반영한다. 이 옵션 자체는 ocarun에 허용하지 않는다. 초기 설치·자격 증명 배치는 이번 VM에서 관리자 작업으로 수행했으며 범용 설치 CLI는 아직 없다.

2026-11-07 관리자 래퍼 및 관측 검사 테스트 21개가 통과했다. 실제 VM에서 다음 명령을 실행해 PASS를 확인했다.

```sh
sudo -u ocarun sudo -n /usr/local/sbin/launchpad-check memory-0.5.0-329179a5f71d
```

결과에는 활성 릴리스·모델/메모리·Langfuse 입출력·메모리 본문 제외 검사와 관측 5개만 출력됐다. 다른 별칭 `memory-0.4.2`, 관리자 `--sudoers` 옵션, 검증 자격 증명 파일 읽기는 ocarun에서 모두 거부됐다. 기존 설치/활성화 sudoers는 유지했다. 이는 실제 Run Command 사용자로 실행한 검증이며 후속 단계가 포함된 새 DevOps 배포 실행을 검증한 것은 아니다.
