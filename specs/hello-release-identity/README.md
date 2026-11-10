# 실행 기록에서 검증한 Hello Agent 소스 알아보기

**새 실행에 업무 명세·소스·테스트 근거의 식별자를 함께 남깁니다.** 같은 앱 버전 문자열을 써도 파일 내용이 다르면 다른 릴리스 ID가 만들어집니다. 앱 시작 시 실제 설치 파일을 확인하고, health·채팅 응답·Langfuse 관측에 같은 해시를 넣습니다.

기존 배포는 설정 없이 계속 실행할 수 있으며 `release: null`을 반환합니다. 과거 실행의 명세 연결은 자동으로 채우지 않습니다. 이 기능은 Hello Agent 전용 선택 기능이며 API·MCP·웹 중 특정 제공 방식을 다른 앱에 강제하지 않습니다.

## 준비

Python 3.12 이상과 Hello Agent의 기존 개발 환경이 필요합니다. 해당 환경에는 FastAPI, httpx, pytest와 앱 의존성이 설치되어 있어야 합니다. `devmrko-python-foundation==0.1.2`는 별도 제공받은 패키지나 접근 권한이 필요하므로 공개 저장소만으로 전체 웹 검증 환경이 준비되지는 않습니다.

이하 명령은 저장소 루트에서 실행합니다. 모델과 OTLP 전송을 로컬 대역으로 검증하므로 OCI 계정·Langfuse 키·실제 모델 호출은 필요하지 않습니다.

```sh
mkdir -p .run
.venv/bin/python scripts/command_evidence.py run \
  specs/hello-release-identity/checks.json \
  --output .run/hello-release-checks.json -- \
  .venv/bin/python -m pytest -q examples/hello-agent \
  deploy/tests/test_hello_oke.py scripts/test_hello_identity.py

python3 -S scripts/build_hello_identity.py \
  --evidence .run/hello-release-checks.json \
  --output .run/hello-release-identity.json
```

첫 명령은 `COMMAND_SUCCEEDED`·`stable_during_run: true`, 두 번째는 `PREPARED`·`cloud_deployed: false`가 정상 결과입니다. 재실행에는 새 출력 경로를 사용합니다. 검증 후 대상 파일을 바꾸면 식별 정보 생성을 거부합니다. 명령 성공 기록은 요구사항을 자동 승인한 결과가 아닙니다.

## 어떤 값을 연결하나요?

| 필드 | 의미 |
|---|---|
| `release_id` | 아래 정보와 앱 버전·파일 목록을 합친 본문의 정규화 SHA-256 |
| `spec_sha256` | `specs/hello-agent/spec.md` 업무 명세의 SHA-256 |
| `source_sha256` | 실행 모듈 4개 이름·SHA-256 묶음의 정규화 해시 |
| `test_evidence_sha256` | 실제 명령 실행 결과 JSON 파일의 SHA-256 |
| `runtime_files` | `agent.py`, `hello_web.py`, `hello_telemetry.py`, `hello_release.py` 각각의 SHA-256 |

업무 명세 검증과 별도로, 이번 릴리스 기능의 요구·테스트 범위는 [명세](spec.md), [설계](design.md), [실행 대상 파일](checks.json)에 있습니다. 실행 파일 해시는 Python·Foundation·OCI SDK 등 모든 의존성의 무결성을 확인하는 값이 아닙니다.

## 새 실행에 적용하기

생성된 JSON 전체를 `HELLO_RELEASE_IDENTITY` 환경 변수로 공급합니다. 앱 시작 시 본문의 release_id와 실제 설치 모듈 해시를 대조합니다. 잘못된 JSON·변조된 해시·바뀐 실행 파일은 시작을 거부합니다. 검증을 조용히 끄고 진행하지 않습니다.

OKE에서는 기존 `render_hello_oke.py` 입력 JSON에 `release_identity` 객체로 넣습니다. 렌더러가 환경 변수와 Pod의 `launchpad.dev/release-id` annotation을 함께 생성합니다. 예를 들어 Python에서 `config['release_identity'] = json.loads(Path(identity_path).read_text())`로 추가한 뒤 기존 렌더러에 넘길 수 있습니다. `image`는 계속 digest로 고정해야 합니다.

이후 정상 실행의 `/health`와 인증된 `/api/chat` 응답에는 같은 `release` 요약이 들어갑니다. 실제 OTLP payload의 루트·모델·도구 observation metadata에도 `release_id`, `spec_sha256`, `source_sha256`, `test_evidence_sha256`을 넣습니다. 입력 메시지나 추가 요청 필드로 이 값을 바꿀 수 없습니다.

## 패키지를 만든 뒤에도 확인하기

빌드에는 `pyproject.toml`에 고정한 setuptools·wheel을 사용합니다. 실제 전달할 wheel을 별도 디렉터리에 설치하고, 그 설치 경로에서 식별 정보를 로딩해 검증하세요. 예시의 `.run/hello-installed`는 새 폴더여야 합니다.

```sh
.venv/bin/python -m pip wheel --no-deps --wheel-dir .run/hello-wheels examples/hello-agent
.venv/bin/python -m pip install --no-deps --target .run/hello-installed \
  .run/hello-wheels/launchpad_hello_agent-0.1.0-py3-none-any.whl
PYTHONPATH=.run/hello-installed .venv/bin/python -c \
  'from pathlib import Path; from hello_release import load; print(load(Path(".run/hello-release-identity.json").read_text()))'
```

라이브러리 버전 `0.1.0`은 현재 알파 예제 버전입니다. 같은 버전으로 만든 파일을 덮어 배포하지 말고 wheel SHA-256·release_id와 원본 테스트 기록을 함께 보관하세요. 이 식별 정보는 전자서명이 아니며 파일과 JSON을 함께 바꿀 권한이 있는 사람의 위조를 방지하지 않습니다.

## 확인한 범위

2026-11-10 로컬에서 테스트 21개(하위 사례 27개), 스크립트 회귀 테스트 107개가 통과했습니다. 실제 wheel을 빌드하고 별도 디렉터리에 설치한 뒤, 생성 도구의 식별 정보를 앱이 로딩하고 health→채팅 응답→관측 3개에 같은 값이 전달되는 것을 확인했습니다. 모델은 로컬 대역, 관측 HTTP는 MockTransport를 사용했습니다.

이번 검증은 새 OCI 배포나 Langfuse 서버 수신 확인을 포함하지 않습니다. 이미지 내부 파일, 실제 Pod와 배포 ID, Langfuse 조회 결과를 새 release_id에 대조하는 클라우드 검증은 남아 있습니다. 현재 Companion의 과거 Hello Agent 기록은 계속 명세·이미지 미연결로 표시합니다.
