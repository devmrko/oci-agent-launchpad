# Service Desk 질문·답변을 Langfuse에서 확인하기

Service Desk의 실제 `/api/chat` 요청과 모델 판단·도구 실행을 선택적으로 Langfuse에 기록한다. Companion에는 관리 링크만 있고, 수집은 앱에서 직접 수행한다. 2026-11-07 구현은 root agent observation과 model.route·tool.<action> 하위 observation이다. 승인 API는 service-desk.approve와 tool.approve로 기록한다. 메모리 저장·검색 호출은 처리 시간·성공 여부·건수를 기록한다. Oracle Agent Memory 내부 SQL·임베딩 개별 단계는 계측하지 않는다.

## 설정

| 변수 | 필수 여부 | 의미 |
|---|---|---|
| DESK_LANGFUSE_CONFIG | 파일 방식 사용 시 필수 | 런타임 JSON 파일 경로. 아래 직접 환경변수 방식과 동시 사용 불가 |
| DESK_LANGFUSE_URL | 직접 환경변수 방식일 때 필수 | 신뢰하는 Langfuse 주소. 미설정 시 계측 비활성 |
| DESK_LANGFUSE_PUBLIC_KEY | 활성화 시 필수 | 대상 프로젝트 public key |
| DESK_LANGFUSE_SECRET_KEY | 활성화 시 필수 | 대상 프로젝트 secret key, 비밀 저장소에서 실행 환경에 주입 |
| DESK_LANGFUSE_CAPTURE_CONTENT | 선택, 기본 꺼짐 | 정확히 true일 때 일반 질문과 최종 답변을 수집. 메모리 본문은 항상 제외 |

본문 수집을 켜기 전에 대상 데이터의 저장 허용 여부를 확인한다. 이번 검증은 합성 업무 데이터만 사용했다. 현재 자동 개인정보 마스킹은 없다. 입력 2000자·출력 8000자로 제한하고 요청 헤더·계정 토큰·전체 응답 객체를 복사하지 않는다. 모델명·리전·사용량은 root metadata의 model에 들어가며 Langfuse generation별 토큰/비용 열을 채운 것은 아니다.

전송은 100건 제한 메모리 큐와 별도 worker에서 수행한다. HTTP timeout 2초, redirect 및 자동 재시도 없음. 큐 포화·전송 실패는 계수와 경고를 남기며 사용자 응답은 유지한다. 디스크 보관·재전송·무손실 보장은 없다. 종료 시 최대 3초 기다리며 남은 데이터가 있으면 경고한다. 프로세스 종료로 대기 이벤트가 유실될 수 있다. 인증 이후 chat 경로의 실패는 root 및 실행한 단계의 ERROR span으로 기록한다. 실패한 단계의 본문과 예외 원문은 제외하고 오류 코드만 보낸다. 인증·요청 스키마 검증에서 차단된 요청은 이 경로에 들어오지 않는다.

## 실제 검증

개발 Mac에서 FastAPI TestClient로 실제 `/api/sessions`와 `/api/chat`을 호출했다. OCI config 인증으로 us-ashburn-1의 google.gemini-2.5-flash-lite를 호출했고 모델은 search 도구를 선택했다. 최종 답변은 앱의 합성 VPN 규정에서 가져왔다. 모델이 최종 문장을 생성한 것으로 해석하지 않는다. ADB memory는 이번 요청에 사용하지 않았다.

- API HTTP 200, mode live-model, 모델 입력 71 / 출력 5 tokens, 모델 소요 1710.15ms.
- Export sent=1 / failed=0.
- request_id: 02203dbc-013a-4ced-a614-c455449f81ff.
- Langfuse trace_id: 49c860fb837cd81096b80d85d1635d78.
- 저장된 출력과 API 응답의 answer 일치 확인.
- Edge 로그인 화면에서 service-desk.chat 상세 Input·Output 표시 확인.
- 추가 계측 3개와 기존 업무 흐름 7개 테스트 통과: 실제 endpoint의 데이터 연결, 본문 기본 제외, 전송 장애 시 HTTP 성공.

이는 로컬 앱 → 실제 OCI 모델 → 서울 Langfuse의 통합 검증이다. 기존 중지된 업무 VM의 재배포나 Companion 빌드·배포 완료를 뜻하지 않는다. 다음 단계는 실제 배포 환경의 secret 참조·송신 경로 설정, 메모리 경로 세부 계측이다.

전체 회귀 점검에서 기존 monitoring 테스트의 입력 검증 기대값(422)을 Foundation의 실제 계약(400 / VALIDATION_FAILED)에 맞추고 오류 코드까지 검사하도록 보완했다.

## 모델·도구 단계 후속 검증

실제 수행 구간의 시작·끝을 측정하고 같은 traceId와 root parentSpanId로 묶는다. 명시적 메모리 요청은 모델을 호출하지 않으므로 모델 span을 만들지 않는다. 모델 미설정의 결정론적 경로는 demo.route / span으로 구분한다. model.route의 출력은 검증 후 선택한 action이며 raw 모델 응답·내부 추론을 수집하지 않는다. tool.search/propose는 실제 반환 답변·출처를 기록하며 메모리 tool의 본문은 제외한다. 본문 수집 옵션을 끄면 하위 단계의 입출력도 제외한다.

2026-11-07 실제 OCI 모델 호출 포함 검증: HTTP 200, 모델 입력 72 / 출력 5 tokens, 모델 구간 1429.86ms. trace `4bd9f83a75368a10c990d5fdaca3c0ab`에서 AGENT(service-desk.chat), GENERATION(model.route), TOOL(tool.search) 3건을 조회했고 모두 input/output 존재와 동일 traceId를 확인했다. 두 하위 기록의 parent는 root `025e7bfb8852c4e3`다. Edge에서 부모·자식 트리와 질문·최종 답변 표시를 확인했다.

전체 pytest 23개 통과. 추가 테스트는 부모·자식 관계와 시간 범위, 도구 출력/API 응답 일치, 모델 실패 시 root/model ERROR와 미실행 도구 기록 부재, 예외 원문·실패 프롬프트 제외를 확인한다. 실제 OCI 실패를 일부러 유발한 것은 아니며 실패 검증은 테스트 대역을 사용했다. 운영 VM 재배포는 아직 하지 않았다.

## 승인 경로 검증 (2026-11-07)

`/api/proposals/{id}/approve`를 service-desk.approve root와 tool.approve 하위 기록으로 연결했다. 기존 Gateway의 권한·소유권 검사와 중복 등록 방지 경로를 그대로 호출한다. 계측은 승인 권한을 부여하거나 우회하지 않는다. 승인 API의 confirmed=true 검증 전에 실패하는 요청은 이번 계측에 들어오지 않는다.

본문 수집을 켠 경우에도 승인 요약문·원문 proposal ID·사용자 ID는 보내지 않는다. 성공 기록에는 confirmed, proposal_ref(SHA-256), status, ticket_ref(SHA-256)만 남긴다. 해시는 반복 요청 대조용 가명 참조이며 익명성을 보장하지 않는다. 실패는 오류 코드만 기록한다. 동일 ticket_ref가 반복된다는 사실을 보여주며, 별도 replay 판정 필드를 만들어 실제 생성/재사용을 구분한 것은 아니다.

로컬 FastAPI 요청 → 실제 서울 Langfuse 통합 시험:

- 권한 없는 계정: HTTP 403, ERROR 기록, 출력 본문 없음. trace c38487ffcabe9792923faf1d7efceb72.
- 정상 승인: HTTP 200, 성공 출력 저장. trace fd3428f259c9adcab603f029c6dd0fcd.
- 동일 초안 재승인: HTTP 200, 저장 티켓 수 1개 유지. trace 20215871edd0e969a38451517138ca94.
- 초안 chat을 포함한 4개 전송 묶음 성공, 실패 0건.
- 전체 테스트 24개 통과. 승인 성공·권한 거부·반복 호출·원문 미노출·부모/자식 관계를 검증했다.

실제 외부 고객 티켓을 생성한 것이 아니라 임시 로컬 DB의 합성 지원 요청이다. 업무 VM 재배포·Companion 빌드/배포는 여전히 미완료이며 이번 검증은 Langfuse API 조회까지다.


## 메모리 저장·검색 관측과 본문 보호 (2026-11-07)

운영자는 기억 내용을 복제하지 않고 저장·검색이 성공했는지, 얼마나 걸렸는지, 몇 건을 반환했는지 확인할 수 있다. 기억의 저장소는 기존 Oracle Agent Memory이며 Langfuse는 실행 관측을 맡는다. Companion과의 실행 의존성은 추가하지 않는다.

| 진입 경로 | 부모 기록 | 하위 기록 |
|---|---|---|
| POST /api/memories | service-desk.memory-save | tool.memory-save |
| POST /api/memories/search | service-desk.memory-search | tool.memory-search |
| chat의 remember:/recall: 등 명시적 명령 | service-desk.chat | tool.memory-save 또는 tool.memory-search |

부모에는 request_id, content_policy=memory-body-excluded, memory_backend=oracle-agent-memory를 남긴다. backend 표기는 연결 대상 종류이며 정상 연결을 증명하지 않는다. 성공하면 부모·하위 기록에 memory_count를 남기고 실패하면 ERROR와 오류 코드만 남긴다. count는 save의 반환 항목 수 또는 search의 검색 결과 수이며 DB 전체 저장 건수가 아니다. 시작·끝 시각은 메모리 호출 전체 소요 시간이다.

DESK_LANGFUSE_CAPTURE_CONTENT=true여도 이 경로의 부모·자식 input/output은 제외한다. 저장 문장, 검색어, 검색 결과 본문, 메모리 ID, 계정 식별자는 내보내지 않는다. 기존 chat의 상위 기록에 메모리 문장이 들어갈 수 있던 경로도 차단했다. 사용자 API 응답에서 기억을 조회하는 기존 동작은 유지한다. 명시적 메모리 명령은 모델을 호출하지 않는다.

로컬 전체 테스트 28개 통과. 추가 4개 조합(API/대화 × 성공/장애)은 저장·검색 각각의 부모·자식 관계, 시간 범위, 오류 상태, 성공 건수, Actor 전달, 모델 미호출과 민감 문자열 미전송을 검증한다. 메모리 저장소와 Langfuse 수신처는 테스트 대역을 사용했다. 이 로컬 시험에서는 테스트 대역을 사용했으며, 실제 ADB·Langfuse 연결은 아래 후속 통합 검증에서 확인했다. 업무 서비스 재배포는 아직 수행하지 않았다. 인증·스키마 검증 단계에서 거부된 요청은 아직 이 계측에 포함하지 않는다.


## 실제 ADB → Langfuse 통합 검증

같은 날 기존 업무 VM에서 최신 Service Desk 소스를 별도 디렉터리로 실행했다. 설치된 0.4.2 서비스는 교체하지 않았다. 메모리 설정·런타임 계정·Instance Principal·임베딩 모델은 기존 구성으로 사용했다. 업무용 SQLite는 임시 파일이며 메모리 저장·검색은 실제 Oracle Agent Memory/ADB를 호출했다.

`check_memory_telemetry.py`는 직접 API 저장/검색과 서로 다른 대화 세션의 저장/검색, 총 4개 요청을 실행한다. 저장한 항목의 ID가 검색 결과에 포함되는지 확인한 다음 request_id로 실제 Langfuse 수신 기록을 대조한다. 검증 결과:

- 메모리 API 4개 요청 HTTP 200, 저장·재검색 성공.
- Langfuse 전송 4개 묶음 성공, 부모·자식 observation 총 8개 수신.
- 부모·자식 연결, 성공 상태, 반환 건수와 시작·종료 시각 확인.
- 모든 관측 기록의 input/output 비어 있음. 합성 기억 문자열·메모리 ID 미포함 확인.
- 합성 메모리 2개는 고유 테스트 Actor 범위에 저장했다. 기존 기억을 삭제하지 않았다.
- trace IDs: `0ca1fd7b0f2e84c441f0b396d4b56df9`, `19ffbc54b35cf71099697893a06cd902`, `1dbf182d92d7446f701f3cd9458ad134`, `403c26467cc07a63f4a292ad9b4c8c2a`.

재실행에는 기존 메모리 런타임 설정, Instance Principal 권한, ADB 접근 허용 및 실행 환경의 의존성이 필요하다. 앱 소스와 스크립트를 검증 디렉터리에 놓고 다음 형태로 실행한다. stdin에는 비밀 저장소에서 읽은 public_key·secret_key JSON을 전달하며 명령행이나 로그에 키를 넣지 않는다.

```sh
PYTHONPATH=<검증 디렉터리> <앱 venv>/bin/python check_memory_telemetry.py \
  --memory-config <기존 런타임 메모리 설정 경로> \
  --langfuse-url <접근 가능한 Langfuse 주소>
```

이번에는 SSH 역방향 터널로 Langfuse에 접근했으며 ADB ACL·방화벽·IAM 정책을 넓히지 않았다. 이는 배포 환경의 상시 네트워크 경로를 검증한 것은 아니다. 실제 Langfuse API로 수신 확인했으며 이번 기록의 브라우저 화면 검증은 하지 않았다. Companion을 통한 새 버전 빌드·배포, 운영 비밀 주입과 상시 통신 경로 구성은 다음 작업이다. 검증에 임시 기동한 업무 VM·ADB는 종료 후 모두 STOPPED 상태를 확인했다. Langfuse 검증 VM은 기존 실행 상태를 유지한다.


## 배포 시 키를 소스·패키지와 분리하기

0.5.0은 `DESK_LANGFUSE_CONFIG`에 지정한 JSON 파일에서도 설정을 읽는다. 파일 필드는 `url`, `public_key`, `secret_key`가 필수이고 `capture_content`는 선택 boolean이며 기본 false다. 이 파일은 VM의 런타임 비밀 설정으로 준비하며 Git·소스 번들·release.zip·Terraform 변수/상태에 키 값을 넣지 않는다. 기존 직접 환경변수 방식과 동시에 지정하면 시작을 거부한다. 파일 교체 후에는 앱 재시작이 필요하다.

권장 배치는 root 소유, 앱 전용 그룹 읽기 권한의 0640 일반 파일이다. 앱이 파일을 바꾸지 못하도록 부모 디렉터리도 관리자가 소유한다. 구현은 일반 파일, 크기 16KiB 이하, 기타 사용자 접근 없음, 그룹 쓰기 없음, 마지막 경로 요소 symlink 없음을 검사한다. Vault에서 이 파일로 비밀을 주입·회전하는 자동화는 아직 없다. 파일 내용을 애플리케이션 로그에 출력하지 않는다.

환경 렌더러의 선택값 `langfuse_config_path`는 model.env에 `DESK_LANGFUSE_CONFIG` 경로만 추가한다. 렌더러가 파일을 생성하거나 키를 읽는 것은 아니다. Companion은 이 설정이나 키를 읽지 않고 독립된 앱 빌드·배포와 관리 링크를 돕는다.

앱 테스트 35개와 환경 렌더러 테스트 6개, 총 41개가 통과했다. 비밀 파일 읽기, 기본 본문 미수집, 잘못된 boolean·공개 읽기·그룹 쓰기·symlink·중복 설정 거부를 포함한다. 앱 소스는 `f06ee98c4a5985eaafaa68445151840c95908260`으로 고정했다.

## 상시 연결의 현재 차이와 다음 적용 순서

실제 조회에서 업무 VM(10.79.1.241)과 Langfuse private LB(10.78.1.46)는 서로 다른 VCN이다. SSH 터널 통합 검증은 이 두 VCN 사이의 상시 경로를 보장하지 않는다. 같은 리전의 사설 IP 통신은 [OCI Local Peering Gateway 구성](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/localVCNpeering.htm)을 기준으로 연결한다.

1. 각 VCN을 소유한 Terraform 상태와 기존 route table을 확인한다. 기존 인터넷·서비스 경로는 보존한다.
2. 두 VCN의 LPG를 연결하고 앱→LB 주소 및 LB→앱 주소의 양방향 경로를 각각 해당 상태에서 관리한다. 같은 route table을 두 상태에서 동시에 소유하지 않는다.
3. observability 모듈의 `ingestion_client_cidrs`에 앱의 사설 /32만 전달한다. 기본 빈 목록이며, 명시한 RFC1918 /32에서 LB의 TCP 8080으로 들어오는 규칙만 추가한다. 이 변수는 peering이나 route를 생성하지 않는다.
4. VM에서 터널 없이 private LB health를 확인하고, 런타임 비밀 파일을 배치한 뒤 새 릴리스를 활성화한다.
5. 배포 앱의 실제 요청과 Langfuse 수신, 재시작 후 유지, 실패 시 이전 릴리스 복구를 확인한다.

후속 적용에서 LPG·양방향 /32 경로·클라이언트 NSG 규칙을 실제 적용했고, 제한된 런타임 비밀 파일을 VM에 배치했다. Vault 자동 주입·회전과 0.5.0 업무 서비스 활성화는 미완료다. 현재 private HTTP 구성은 합성 검증용이며 운영 TLS 구성은 별도 단계다.


### 사설 경로 후속 실측

2026-11-07 업무 VM에서 private LB health `OK / 4.76.0`을 확인했다. 앱 계정 UID 987로 격리된 0.5.0 소스를 실행해 런타임 비밀 파일을 읽고 관측 기록 3개를 직접 전송했다. 실제 수신 trace는 `fcfdac5ced485ee8144e311a28be9bcb`, 본문 수집 false이며 관측 input/output은 비어 있었다. 실제 모델·ADB 호출 없이 합성 업무 검색으로 네트워크와 설정 주입을 확인했다. 설치된 0.4.2 서비스는 교체하지 않았다. [네트워크 상태 소유와 적용 절차](../infra/terraform/peering/README.md)를 따른다.


## 0.5.0 서비스에 상시 연결 적용 (2026-11-07)

실제 systemd 서비스가 0.5.0으로 전환되어, 별도 TestClient나 SSH 역방향 터널 없이 사설 VCN → Langfuse LB로 관측을 전송한다. OCI 관리형 빌드와 Artifact Registry 전달은 모두 SUCCEEDED였으며, 검증된 패키지를 새 Terraform workspace `bootstrap-050`으로 배포했다. 기존 0.4.1·0.4.2 설치와 허용 별칭은 유지한다. 신규 배포 자원 8개 생성·기존 정책 1개 수정, 삭제 없음. 후속 릴리스 plan은 No changes였다.

- DevOps 배포: `ocid1.devopsdeployment.oc1.ap-seoul-1.amaaaaaavsea7yiaffk2hyzioysrvqawz5xikxez7lzf2xuz7hwffe2voooa` / SUCCEEDED.
- `/health`: UP, version 0.5.0. 미인증 요청 차단·인증된 capability 계약·실제 OCI 모델 호출·세션 간 실제 Oracle Agent Memory 저장/조회·앱 추적에서 메모리 내용 제외 검사 통과. 검증은 합성 업무 데이터이며 synthetic memory 1건을 추가했다.
- `DESK_LANGFUSE_CONFIG=/etc/launchpad/langfuse.json`. 키는 제한된 root:launchpad 0640 파일에 유지하고 환경변수에는 경로만 둔다. 일반 합성 데모 입력·출력을 보기 위해 이 환경의 `capture_content=true`를 명시했다. 제품 기본값은 false이며 메모리 내용은 true여도 제외한다.
- 별도 실제 모델 요청과 메모리 검색에서 관측 5건 수신을 확인했다. 일반 대화 root·model.route·tool.search의 3건과 메모리 검색 root·tool 2건이다. 대화 root 입력·출력 존재 및 메모리 관측 입력·출력 부재를 검사했다.
- 검증 trace: `0b2e252549d232c414160f0560f4776e`, `e6ce71079135eb146cb544ffffbaaa28`. API로 수신·내용 정책을 검증했으며 이 두 trace의 브라우저 화면은 아직 별도로 확인하지 않았다.

이번 빌드·배포 시작은 OCI SDK였다. Companion 브라우저 자동화 차단이 남아 있으므로 Companion 버튼을 통한 전체 완주로 표현하지 않는다. 빌드 결과 다운로드 검증과 root manifest 등록은 운영자 절차이며 아직 Companion의 단일 자동 배포 기능이 아니다. 비동기 관측은 메모리 큐 기반 best-effort이고, 서비스 재시작 시 미전송 이벤트 보존·디스크 큐·재전송 보장은 없다.

VM·ADB·관측 서비스는 검증 후 실행 상태로 유지했다. 원격 HTTPS·고가용성·운영 인증은 이 합성 단일 VM 검증의 완료 범위가 아니다.
