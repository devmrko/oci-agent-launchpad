# 사내 안내·요청 접수 예제

직원이 규정을 찾고 지원 요청 초안을 확인한 뒤 접수하는 과정을 직접 실행합니다. 현장 엔지니어는 이 예제로 고객의 업무 의도를 요구·설계·코드·검증으로 연결하는 방법을 익힐 수 있습니다.

합성 규정과 합성 접수함을 사용합니다. 기본 실행은 규칙 라우터이며 실제 LLM 추론은 하지 않습니다. Python Foundation이 인증·오류·DB 트랜잭션을 담당하고, 예제 앱이 업무 규칙·승인·사용자별 상태를 담당합니다. 전체 AgentCore 대체 플랫폼의 완성본은 아닙니다.

## 처음 실행하기

Python 3.12 이상과 고정 버전의 python-foundation 소스가 필요합니다. 실제 검증 환경은 Python 3.14/macOS입니다. 저장소 접근에는 각 저장소의 GitHub 권한이 필요합니다. 토큰을 URL이나 명령에 넣지 마세요.

```bash
git clone https://github.com/devmrko/python-foundation.git /원하는/경로/python-foundation
git -C /원하는/경로/python-foundation checkout c98f69dd20c005ac5aa244dd03f110ddeed368dd
cd examples/service-desk
PYTHON=python3.14 bash scripts/setup.sh /원하는/경로/python-foundation
.venv/bin/python scripts/run_demo.py
```

기존 Foundation 작업 폴더가 있다면 변경 사항을 보존하고 별도 clone을 사용하세요. 위의 `/원하는/경로`는 실제 디렉터리로 바꿉니다. 실행 후 `http://127.0.0.1:8092/docs`에서 API 명세를 볼 수 있습니다. 자동 생성한 로컬 인증키는 `.run/demo-accounts.json`에 저장하며 Git에서 제외합니다. 서버는 로컬 루프백 주소에서만 수신합니다.

다른 터미널에서 같은 예제 디렉터리로 이동해 실행합니다.

```bash
.venv/bin/python scripts/smoke.py
.venv/bin/python -m pytest -q
```

첫 명령은 실행 중인 서버에 규정 조회→초안→승인→중복 승인→추적 조회를 요청합니다. `result: PASS`이면 네 가지 검증이 통과한 것입니다. 실행할 때마다 합성 요청 한 건을 추가합니다. 두 번째 명령은 임시 DB로 소유권·권한·재시작·동시 승인 등도 시험합니다.

## 따라가 볼 업무 흐름

1. `POST /api/sessions`로 자신의 세션을 만듭니다.
2. `POST /api/chat`에 세션 ID와 “VPN 규정”을 넣으면 `POL-VPN-01` 출처를 받습니다.
3. “VPN 장애 접수”를 입력하면 `proposal_id`와 확인할 내용이 나오며 접수는 아직 발생하지 않습니다.
4. `POST /api/proposals/{proposal_id}/approve`에 `{"confirmed":true}`를 보내면 접수됩니다. 같은 제안을 다시 승인해도 한 건만 생깁니다.
5. `GET /api/traces`로 자신의 실행 기록을 확인합니다. 응답의 `x-request-id`와 대조합니다.
6. `PUT /api/memory`에 `{"language":"en"}`을 넣으면 다음 세션에서도 영어 규정을 사용합니다. `DELETE /api/memory`로 지웁니다.

업무 API에는 `Authorization: Bearer <로컬 생성 키>`가 필요합니다. 추적에는 자유 입력 원문을 담지 않지만 요청 초안·접수에는 합성 입력이 저장됩니다. 실제 개인·고객 데이터를 넣지 않는 예제입니다.

## 설정과 한계

| 설정 | 구분 | 내용 |
| --- | --- | --- |
| DESK_AUTH_MODE | 필수, 기본 demo | demo 또는 jwt. 실행 스크립트는 demo로 고정 |
| DESK_DEMO_ACCOUNTS | demo일 때 필수 | 토큰을 키로, subject/can_write를 값으로 한 JSON. 스크립트가 로컬 생성 |
| DESK_DATABASE_URL | 옵션, jwt에서는 필수 | 기본 SQLite. 스크립트는 `.run/desk.db` 사용 |
| DESK_MODEL_URL / KEY / NAME | 실제 모델 사용 시 모두 필수 | HTTPS OpenAI 호환 chat completions URL, API 키, 모델 이름 |
| Foundation 인증 설정 | jwt일 때 필수 | 고정 Foundation의 issuer/audience/jwks_url 설정 규약 참조 |

실제 모델은 search/propose 선택만 제안합니다. 서버가 허용 목록과 승인·소유권을 검사하며 모델이 접수를 직접 실행하지 않습니다. 실제 OCI 모델 연결은 아래 검증 범위에 포함됩니다. JWT 공급자 연결과 업무 데이터의 SQLite 외 DB 전환은 아직 검증하지 않았습니다. [Oracle Linux VM 배포·원격 시험](../../deploy/README.md)은 완료했습니다. 모델 옵션은 로컬 스크립트 실행 전에 환경변수로 공급할 수 있습니다.

현재 자동 테이블 생성은 개발 편의를 위한 것입니다. 운영 전에는 마이그레이션, 보관·삭제 정책, TLS, 운영 인증, 페이지별 조회 제한, 관측 백엔드와 복구 절차를 갖춰야 합니다. 코드 실행 sandbox·브라우저·MCP Gateway는 구현하지 않았습니다.

## 설계와 다음 단계

- [AI-DLC 설계와 질문 예시](aidlc/design.md)
- [고객에게 작성받을 상세 양식](../../templates/use-case.md)
- [Companion 연결과 배포 준비](../../docs/companion-integration-plan.md)
- [검증 기록](aidlc/verification.md)

## 0.2 실제 모델과 공통 Gateway

Foundation 0.1.1의 공통 ToolGateway가 입력 스키마·권한·자원 정책·실행 예산과 도구 이벤트를 처리합니다. `GET /api/tools`로 도구 명세를 조회합니다. 이 기능은 인프로세스 Gateway이며 네트워크 MCP 서버는 아닙니다.

OCI 모델은 `DESK_MODEL_BACKEND=oci`, `DESK_OCI_REGION`, `DESK_OCI_COMPARTMENT`, `DESK_MODEL_NAME`으로 설정합니다. VM은 `DESK_OCI_AUTH=instance`, 로컬 검증은 `config`를 사용합니다. 모델은 검색 또는 초안 생성만 선택하고 승인 권한은 갖지 않습니다. 원격 API 호출 제한시간 25초, 출력 128토큰, 자동 재시도 없음입니다.

실제 모델 호출 경로는 애슈번입니다. 서울 Flash Lite와 Flash의 활성 목록을 확인했으나 실제 공급자 호출은 실패했고, 애슈번 Flash Lite 합성 질문은 성공했습니다. VM·SQLite는 서울입니다. `trace.model`에 모델·리전·토큰·지연을 표시하고 `trace.tools`에 공통 도구 실행 단계를 표시합니다. 실제 사용자 로그인·비용 계산·MCP·긴 작업·sandbox·브라우저는 이 버전의 완료 범위가 아닙니다.

## Oracle Agent Memory (0.3.0)

새 ADB를 사용하는 선택 기능입니다. [구성·API·실제 검증](../../docs/oracle-agent-memory.md)을 참고하세요. `requirements-memory.lock`은 VM에서 검증된 전체 의존성입니다. 일반 데모의 언어 설정과 장기 기억 API는 별개이며, 자동 추출·채팅 자동 주입은 아직 제공하지 않습니다.

## 채팅 기억 (0.4.0)

`기억해 주세요: …`로 저장하고 `기억에서 찾아 주세요: …`로 다른 세션에서도 조회합니다. 기억은 출처 ID와 함께 표시되며 업무 실행 지시로 처리하지 않습니다. 일반 대화 자동 저장·개인화는 아직 없습니다. 실제 OCI 검증 스크립트는 `scripts/smoke_memory_chat.py`입니다.

## 배포한 0.4.2의 동작 확인

운영자가 배포 버전과 대표 기능을 반복 확인할 수 있도록 독립 HTTP 검증 CLI를 제공합니다. 예제 디렉터리에서 실행합니다. `httpx`가 설치된 Python 환경과 이미 발급한 평문 토큰 파일이 필요합니다. 아래 주소는 SSH 터널의 예이며 실제 주소로 바꾸세요. 외부 서버에는 HTTPS를 사용하고 토큰을 명령 인자에 직접 넣지 않습니다.

```sh
python scripts/check_runtime.py \
  --base-url http://127.0.0.1:8094 \
  --token-file /secure/path/demo-token \
  --expected-version 0.4.2 \
  --model --memory
```

| 인자 | 필수/옵션 | 검사 범위 |
|---|---|---|
| `--base-url` | 필수 | 앱 주소 또는 기존 SSH 터널 주소 |
| `--token-file` | 필수 | 인증용 토큰 파일; 출력하지 않음 |
| `--expected-version` | 필수 | health·기능 계약·새 실행 추적의 기대 버전 |
| `--model` | 옵션, 기본 꺼짐 | 합성 VPN 규정 질문으로 OCI 모델 호출·출처·추적 버전 확인 |
| `--memory` | 옵션, 기본 꺼짐 | 합성 기억 한 건 저장, 새 세션 검색, 기록된 추적에서 원문 제외 확인 |

옵션 없이 실행하면 health·버전·미인증 요청 거절·인증된 9개 기능 계약만 검사합니다. `--model`과 `--memory`는 실제 OCI 호출 비용이 발생할 수 있으며 세션·실행 추적을 추가합니다. `--memory`의 합성 기억은 자동 삭제하지 않습니다. 이전 기록 보존은 별도 `smoke_memory_api.py verify`로 검사합니다.

성공은 JSON `result: PASS`와 종료 코드 0, 실패는 `result: FAIL`과 종료 코드 1입니다. 연결 실패라면 앱 상태뿐 아니라 터널 프로세스도 확인하세요. HTTP 오류는 상태 코드만 출력하고 응답 원문을 노출하지 않습니다.

2026-11-06 staging 사전 점검 적용 후 기존 0.4.2를 OCI SDK로 재배포해 SUCCEEDED를 확인했습니다. 위 명령의 모든 옵션, 기존 Oracle 기억 보존, 잘못된 기대 버전의 실패 종료를 실제 확인했습니다. Companion 화면에서 요청한 재배포 또는 관리형 빌드 성공을 의미하지 않습니다.
