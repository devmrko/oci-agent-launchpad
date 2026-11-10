# 내 에이전트에 모델·MCP·실행 추적 연결하기

이 예제는 등록한 사용자 앱이 요청을 받아 **모델로 계산 인자를 정하고 → 별도 MCP 도구를 실행하고 → 응답과 실행 기록을 남기는** 흐름을 보여 줍니다. 플랫폼은 앱의 설정·실행·호출·요청 기록을 관리하고, `connections.py`는 이 계산 앱이 소유한 연결 로직입니다. 기존 Python·Java 앱에 이 코드나 특정 SDK를 강제하지 않습니다.

| 구성 | 역할 |
|---|---|
| 사용자 앱 | 최대 한 번의 모델 호출로 곱셈 인자를 선택·검증하고 결과 반환 |
| OCI SDK / OpenAI 호환 HTTP | 설정에 따라 모델 연결 방식 선택 |
| 공식 MCP Python SDK | 별도 HTTP 서버의 `multiply` 도구 조회·호출 |
| Launchpad 관리 서버 | 앱별 설정 주입, 앱 ID로 호출, 최근 100개 요청의 상태·시간 기록 |
| Langfuse (선택) | 같은 trace ID로 에이전트·모델·도구 관측, 모델명·토큰 수 기록 |

## 계정 없이 연결 경로 검증

Python 3.12 이상, macOS·Linux 기준입니다. 저장소 루트에서 전용 가상 환경을 만듭니다.

```sh
python3 -m venv .run/connected-venv
.run/connected-venv/bin/python -m pip install -r examples/bring-your-agent/connected/requirements.txt
.run/connected-venv/bin/python scripts/connected_agent_demo.py --output .run/connected-check
```

`CONNECTED_AGENT_PASS`와 `result: 42`를 확인합니다. 이 실습은 모델만 HTTP 테스트 대역이며 **실제 LLM 호출은 아닙니다**. 관리 실행기·별도 앱 프로세스·MCP 서버는 실제 실행합니다. 허용하지 않은 모델의 도구 선택 거부, MCP 중단 시 실패 단계 기록, 비밀값의 로그 제외도 확인합니다. 종료 시 실습 프로세스를 정리하고 결과는 출력 폴더에 남깁니다. 다시 실행할 때는 새 출력 경로를 사용하세요.

## 실제 모델로 실행

실제 호출에는 모델 사용 권한과 사용료가 필요합니다. 두 터미널에서 MCP 도구와 관리 서버를 각각 유지합니다. 관리 서버의 PATH에 위 가상 환경을 넣어 등록 앱이 설치한 의존성을 사용하도록 합니다.

```sh
.run/connected-venv/bin/python examples/bring-your-agent/connected/calculator_mcp.py --port 8097
```

```sh
PATH="$PWD/.run/connected-venv/bin:$PATH" python3 deploy/user_apps.py --state .run/connected-runtime serve --port 8096
```

8096을 기존 관리 서버가 사용 중이면 기존 서버를 사용하거나 새 상태 폴더와 포트를 선택합니다. 플랫폼 전체의 Python 환경을 바꾸고 싶지 않다면, 프로젝트를 복사하고 `app.json`의 `run[0]`에 전용 Python의 절대 경로를 지정할 수도 있습니다.

운영자만 읽을 설정 JSON을 공개 저장소 밖에 준비합니다. 아래는 OCI SDK 방식입니다.

```json
{
  "env": {
    "AGENT_PROVIDER": "oci-sdk",
    "AGENT_MODEL": "google.gemini-2.5-flash-lite",
    "AGENT_OCI_REGION": "us-ashburn-1",
    "AGENT_OCI_COMPARTMENT": "YOUR_COMPARTMENT_OCID",
    "AGENT_OCI_CONFIG": "/absolute/path/to/.oci/config",
    "AGENT_OCI_PROFILE": "DEFAULT",
    "AGENT_MCP_URL": "http://127.0.0.1:8097/mcp"
  },
  "secret_files": {}
}
```

모델·리전·구획은 자신의 권한과 지원 범위에 맞게 설정합니다. 현재 예제의 OCI SDK 인증은 로컬 config 프로필입니다. 클라우드 인스턴스/워크로드 인증까지 이 예제에 구현했다고 보지 마세요.

OpenAI 호환 방식은 `AGENT_PROVIDER=openai-compatible`, `AGENT_MODEL`, `AGENT_BASE_URL`(예: 공급자가 제공한 `/v1`까지의 주소)을 지정합니다. 기본 인증은 API 키이며 `secret_files`에 `AGENT_API_KEY`와 비밀 파일의 절대 경로를 지정합니다. OCI IAM 서명으로 호환 API를 호출하려면 `AGENT_OPENAI_AUTH=oci-config`, `AGENT_OCI_CONFIG`, `AGENT_OCI_PROFILE`, `AGENT_OCI_COMPARTMENT`를 함께 설정합니다. OCI에는 `CompartmentId` 헤더를 전달합니다. 자동으로 다른 공급자나 데모 모드로 전환하지 않습니다.

```sh
chmod 600 /absolute/path/to/settings.json /absolute/path/to/api-key.txt
python3 deploy/user_apps.py --state .run/connected-runtime configure connected-agent /absolute/path/to/settings.json
python3 deploy/user_apps.py --state .run/connected-runtime register examples/bring-your-agent/connected
python3 deploy/user_apps.py --state .run/connected-runtime deploy connected-agent v1
python3 deploy/user_apps.py --state .run/connected-runtime invoke connected-agent '{"message":"6 곱하기 7을 계산해 주세요"}'
python3 deploy/user_apps.py --state .run/connected-runtime requests connected-agent
```

API 키를 쓰지 않으면 `chmod` 명령에서 해당 파일을 제외합니다. 설정 변경은 **다음 배포 시점**에 적용되며 같은 앱 버전을 다시 배포할 수 있습니다. 복구할 때도 현재 설정을 읽으므로 코드 복구가 비밀값·설정의 과거 버전 복구를 뜻하지 않습니다. `configure`는 원본 설정을 private 상태 폴더에 복사하지만 비밀 파일은 참조만 저장하고 배포 때 읽습니다. 빌드에는 설정·비밀을 전달하지 않습니다. `PATH`, `HOME`, `PYTHON*` 등 실행 환경을 바꾸는 변수는 설정 파일에서 받지 않습니다.

MCP 접속은 `AGENT_MCP_URL`로 지정하고 필요한 서버에는 `secret_files.AGENT_MCP_TOKEN`을 설정할 수 있습니다. 공개 서버는 HTTPS만 허용합니다. 제공된 계산 서버는 loopback 전용이며 외부에 공개하는 인증 서버가 아닙니다. MCP 도구가 반환한 설명이나 모델 응답이 허용 목록을 확대하지 않습니다. 이 예제는 `multiply`와 -1000~1000 정수 두 개만 허용하고 결과도 검산합니다.

## 운영 화면과 추적

[Companion 확장](../../../integrations/companion/README.md)의 `/applications`에서 `connected-agent`의 메시지에 계산 요청을 입력하고 **앱 호출**을 누릅니다. 기존 관리 서버의 상태 디렉터리와 Companion 설정이 같아야 합니다. **요청 기록·실패 단계**에서 요청 ID, 버전, 성공·실패, 소요 시간과 예제가 보고한 모델·MCP 단계를 확인합니다. 호출 API는 앱의 임시 포트 대신 앱 ID를 사용합니다. 일반 서비스용 공개 고정 URL이나 무중단 라우터는 아닙니다.

Langfuse를 사용하려면 `env.AGENT_LANGFUSE_URL`, `secret_files.AGENT_LANGFUSE_PUBLIC`, `secret_files.AGENT_LANGFUSE_SECRET`을 추가한 뒤 다시 배포합니다. `telemetry=exported`는 수집 API가 수락했다는 뜻입니다. 저장·조회 완료는 Langfuse에서 같은 trace ID를 검색해서 확인해야 합니다. `telemetry=failed`여도 이미 성공한 도구 실행을 반복하지 않습니다.

관리 기록과 기본 예제 trace에는 사용자 입력·답변 본문을 저장하지 않습니다. 모델명·토큰 수·상태·시간만 보내며 비용을 임의 계산하지 않습니다. 앱이 직접 출력한 로그의 민감 정보까지 플랫폼이 자동 제거하는 것은 아닙니다. 앱별 계측을 추가하지 않은 일반 앱은 플랫폼의 요청 상태·시간만 기록됩니다.

## 검증한 범위

2026-11-10 로컬 관리 앱에서 OCI SDK와 OCI OpenAI 호환 API를 각각 실제 호출하고, 공식 MCP SDK의 별도 계산 서버를 거쳐 `42`를 반환했습니다. 운영 화면에서도 실제 요청에 성공했으며 Langfuse에서 루트·모델·도구 관측 3개와 입력 67·출력 15·총 82토큰을 재조회했습니다. 이는 해당 요청의 측정값입니다. API 키 방식은 로컬 HTTP 테스트 대역으로 인증 헤더·응답 형식을 확인했으며, 모든 공급자와 모델의 호환성을 보장하지 않습니다.

모델 timeout, 허용하지 않은 도구/인자, MCP 중단, 계측 전송 실패, 앱별 비밀 분리와 빌드 미전달을 테스트했습니다. 자동 재기동·공개 서비스 라우팅·컨테이너 격리·OCI 일반 앱 자동 배포는 아직 별도 범위입니다. 모델 응답을 기다리는 동안 동일 앱에 들어온 추가 호출은 거부하며, 실패·시간 초과 요청을 자동 재시도하지 않습니다. timeout은 원격 작업 취소를 보장하지 않습니다.

연결 방식 근거: [OCI Chat Completions](https://docs.oracle.com/en-us/iaas/Content/generative-ai/chat-completions-api.htm), [Oracle의 인증·구획 헤더 예제](https://github.com/oracle-samples/oci-openai), [공식 MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [Langfuse 토큰 기록](https://langfuse.com/docs/observability/features/token-and-cost-tracking).
