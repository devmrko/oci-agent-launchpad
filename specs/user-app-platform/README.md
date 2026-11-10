# 사용자가 만든 에이전트 배포·운영하기

개발자가 Python·Java 등으로 작성한 앱을 등록하면 플랫폼이 빌드, 버전별 실행, 상태·로그 조회와 이전 버전 복구를 담당합니다. 앱은 자신의 LLM SDK, OpenAI 호환 클라이언트, MCP 도구와 프레임워크를 선택합니다. Foundation이나 SDD 문서는 실행의 필수 조건이 아닙니다.

현재 구현은 **신뢰하는 코드를 실행하는 macOS·Linux 단일 운영자용 로컬 백엔드**입니다. HTTP readiness를 제공하는 Python 앱과 Java JAR을 실제 검증했습니다. 브라우저 파일 업로드·Git 가져오기, 다중 사용자 격리, OCI 자동 배포는 아직 제공하지 않습니다. 등록 경로는 관리 서버에 이미 있는 프로젝트 폴더입니다.

## 계정 없이 전체 흐름 확인

Python 3.12 이상과 JDK 21의 `java`, `javac`, `jar`가 PATH에 있어야 합니다. 추가 Python 패키지나 OCI 계정은 필요 없습니다. 저장소 루트에서 실행합니다.

```sh
python3 scripts/user_app_demo.py --output .run/my-user-app-demo
```

JDK가 PATH에 없으면 `--java-home /absolute/path/to/jdk-home`을 지정합니다. 기존 출력 폴더는 덮어쓰지 않습니다. `USER_APPS_PASS`가 나오면 두 언어 모두 다음 흐름이 완료된 것입니다.

1. v1 소스 등록·빌드·실행 → 실제 HTTP 응답 `result=42`
2. 수정한 v2 빌드·배포 → `result=84`
3. 시작에 실패하는 버전 배포 → 기존 v2 PID·포트·응답 유지
4. v1 복구 → `result=42`, 버전별 실행 로그 확인

결과는 출력 폴더의 `summary.json`에 남습니다. 실습 서버와 앱 프로세스는 종료됩니다. 모델 호출·클라우드 배포는 수행하지 않습니다.

## 내 앱 등록하기

프로젝트 루트에 `app.json`을 둡니다. [Python 예제](../../examples/bring-your-agent/python/app.json)와 [Java 예제](../../examples/bring-your-agent/java/app.json)는 플랫폼 라이브러리를 import하지 않습니다.

```json
{
  "schema_version": 1,
  "id": "my-agent",
  "version": "v1",
  "files": ["app.py"],
  "build": [],
  "run": ["python3", "app.py", "{port}"],
  "health_path": "/ready"
}
```

`files`는 복사할 상대 경로의 명시적 목록입니다. `build`는 argv 배열들의 목록, `run`은 실행할 argv 배열입니다. 셸 문자열은 받지 않습니다. 앱은 전달받은 포트와 `BIND_HOST`에서 HTTP를 열고 `health_path`에 200을 반환해야 합니다. `PORT`와 `APP_VERSION`도 환경 변수로 전달됩니다. API·웹 앱·HTTP 기반 MCP 서버에 적용할 수 있지만 현재 실증은 두 HTTP 예제에 한정됩니다. stdio 전용 MCP나 배치 작업은 별도 실행 규약이 필요합니다.

첫 터미널에서 관리 서버를 실행하고 유지합니다.

```sh
python3 deploy/user_apps.py --state .run/my-apps serve --port 8096
```

두 번째 터미널에서 등록·배포합니다.

```sh
python3 deploy/user_apps.py --state .run/my-apps register examples/bring-your-agent/python
python3 deploy/user_apps.py --state .run/my-apps deploy user-python v1
python3 deploy/user_apps.py --state .run/my-apps status
python3 deploy/user_apps.py --state .run/my-apps logs user-python v1
```

`status`의 URL로 앱에 접속합니다. v2는 소스와 manifest의 version을 수정해 새로 등록합니다. 동일 버전 덮어쓰기는 거부하며 등록 후 원본 수정은 등록된 복사본에 영향을 주지 않습니다.

```sh
python3 deploy/user_apps.py --state .run/my-apps rollback user-python
python3 deploy/user_apps.py --state .run/my-apps stop user-python
```

복구는 이전 성공 버전이 있어야 합니다. 새 버전이 준비되면 기존 프로세스를 종료하므로 **포트가 바뀝니다**. 고정 주소의 트래픽 전환이나 무중단 배포를 보장하지 않습니다. 관리 서버 종료 시 소유 앱도 종료하며, 재시작하면 등록 버전은 남지만 자동 재실행하지 않습니다.

## 화면에서 운영하기

[Companion 확장 설치](../../integrations/companion/README.md) 후 `/applications`에서 서버 프로젝트 경로 등록, 버전 선택·배포, 복구·중지와 빌드/실행 로그 조회를 제공합니다. 상태는 페이지 조회 시 확인합니다. 장기 메트릭 수집·알람은 아직 제공하지 않습니다. 선택적으로 호출 경로를 선언하면 앱 ID로 호출하고 최근 100개의 요청 상태·시간을 확인합니다. 상세 모델·도구 관측은 앱에서 연결합니다.

서버 실행 시 다음 설정을 추가합니다.

```sh
--companion.user-app-state=/absolute/path/to/.run/my-apps
--companion.user-app-scope=/absolute/path/to/scope.json
```

`scope.json`은 기존 [Companion 근거 화면의 접속 범위](../companion-evidence/README.md)와 같은 구조이며 로그인 범위와 정확히 일치해야 합니다. 관리 API는 loopback만 열고 상태 폴더의 토큰으로 인증합니다. Companion이 서버 측에서 이 토큰을 읽으며 브라우저에는 전달하지 않습니다. 토큰·범위 파일을 공개 저장소에 올리지 마세요.

관리 API는 `GET /apps`, `POST /command`를 제공합니다. CLI와 화면이 같은 API를 사용합니다. POST의 `action`은 `register`, `deploy`, `rollback`, `stop`, `logs`이며 인자는 위 CLI와 같습니다.

## OCI 배포로 확장하기

`deploy/render_user_app_oke.py`는 같은 실행 규약으로 ServiceAccount·Deployment·ClusterIP Service JSON을 생성합니다. 이미지를 직접 빌드하거나 레지스트리에 올리거나 클러스터에 적용하지 않습니다.

대상 파일 예시입니다. 이미지 digest는 실제 빌드·검증한 값으로 교체합니다.

```json
{
  "namespace": "user-agents",
  "image": "registry.example/agent@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "port": 8080,
  "working_directory": "/app"
}
```

```sh
python3 deploy/render_user_app_oke.py \
  --manifest examples/bring-your-agent/python/app.json \
  --target /absolute/path/to/target.json --output .run/my-oke-resources
```

컨테이너에는 앱 산출물과 실행 도구가 있어야 합니다. namespace 생성, 레지스트리 인증, 네트워크, 리소스 용량 및 앱별 쓰기 경로는 운영자가 준비·검토해야 합니다. 기본값은 non-root, 읽기 전용 root 파일시스템과 `/tmp`이며 필요에 맞게 검토해야 합니다. 두 언어의 명령·readiness 변환을 테스트했지만 이 일반 앱 경로의 실제 OKE 배포는 아직 검증하지 않았습니다.

## 현재 실행 경계

등록·빌드는 운영자 권한으로 코드를 실행합니다. 파일 목록 검사와 토큰 인증이 비신뢰 코드 샌드박스를 대신하지 않습니다. 앱 로그에 기록한 민감 정보는 자동 마스킹되지 않습니다. 관리 서버의 공급자 자격 증명·전체 환경을 자동 상속하지 않습니다. 앱별 `configure`에서 실행 환경과 비밀 파일 참조를 명시할 수 있습니다. 컨테이너 격리·공개 고정 호출 주소·장애 후 재기동은 후속 범위입니다.

## 실제 LLM·MCP 연결

[연결된 사용자 에이전트](../../examples/bring-your-agent/connected/README.md)는 OCI SDK / OpenAI 호환 연결을 선택하고 MCP 도구 실행·Langfuse 추적을 연결합니다. `app.json`의 선택 필드 `invoke_path`는 POST를 받을 앱 경로이며, `configure`, `invoke`, `requests`를 CLI와 인증된 관리 API에서 사용합니다. Companion에서도 메시지 호출과 요청 기록을 확인합니다. 언어·프레임워크나 계측 SDK를 실행의 필수 조건으로 추가하지 않습니다.

[설계와 검증 범위](design.md)
