# 사내 안내·요청 접수 예제

직원이 규정을 찾고 지원 요청 초안을 확인한 뒤 접수하는 과정을 직접 실행합니다. 현장 엔지니어는 이 예제로 고객의 업무 의도를 요구·설계·코드·검증으로 연결하는 방법을 익힐 수 있습니다.

합성 규정과 합성 접수함을 사용합니다. 기본 실행은 규칙 라우터이며 실제 LLM 추론은 하지 않습니다. Python Foundation이 인증·오류·DB 트랜잭션을 담당하고, 예제 앱이 업무 규칙·승인·사용자별 상태를 담당합니다. 전체 AgentCore 대체 플랫폼의 완성본은 아닙니다.

## 처음 실행하기

Python 3.12 이상과 고정 버전의 python-foundation 소스가 필요합니다. 실제 검증 환경은 Python 3.14/macOS입니다. 저장소 접근에는 각 저장소의 GitHub 권한이 필요합니다. 토큰을 URL이나 명령에 넣지 마세요.

```bash
git clone https://github.com/devmrko/python-foundation.git /원하는/경로/python-foundation
git -C /원하는/경로/python-foundation checkout e8798f9397d6391d39d9159a801dfa5ec7908663
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

실제 모델은 search/propose 선택만 제안합니다. 서버가 허용 목록과 승인·소유권을 검사하며 모델이 접수를 직접 실행하지 않습니다. 실제 모델 연결, JWT 공급자 연결, SQLite 외 DB, 클라우드 배포는 아직 검증하지 않았습니다. 모델 옵션은 로컬 스크립트 실행 전에 환경변수로 공급할 수 있습니다.

현재 자동 테이블 생성은 개발 편의를 위한 것입니다. 운영 전에는 마이그레이션, 보관·삭제 정책, TLS, 운영 인증, 페이지별 조회 제한, 관측 백엔드와 복구 절차를 갖춰야 합니다. 코드 실행 sandbox·브라우저·MCP Gateway는 구현하지 않았습니다.

## 설계와 다음 단계

- [AI-DLC 설계와 질문 예시](aidlc/design.md)
- [고객에게 작성받을 상세 양식](../../templates/use-case.md)
- [Companion 연결과 배포 준비](../../docs/companion-integration-plan.md)
- [검증 기록](aidlc/verification.md)
