# 환경 변수로 앱과 Companion 연결하기

환경별 코드 복사를 줄이기 위해 `environment.example.json`의 값을 바꾸고 인프라 출력과 결합합니다. 생성기는 설정 파일만 만들며 클라우드 변경, 원격 명령 실행, 비밀값 조회는 하지 않습니다.

## 하나의 환경 설정

리전·구획·OCI 연결 사용자, 채팅 모델, 임베딩 모델·차원, 메모리 스키마·실행 계정·저장소 ID·namespace, Companion 터널 포트와 토큰 파일 경로를 설정합니다. 샘플의 placeholder는 실제 값으로 바꿔야 합니다. DB 암호·DSN·API 토큰은 이 파일에 넣지 않습니다.

```sh
cp deploy/environment.example.json .run/customer-environment.json
# 값 수정 후, Terraform을 실제 적용한 환경에서 출력
terraform -chdir=infra/terraform output -json > .run/customer-infra.json
python3 deploy/render_environment.py \
  --environment .run/customer-environment.json \
  --terraform-output .run/customer-infra.json \
  --output-dir .run/customer-config
```

생성 파일은 권한 0600으로 저장합니다.

| 출력 | 용도 |
|---|---|
| `model.env` | 앱 모델 호출 설정·메모리 설정 파일 경로. ADB 미생성 시 메모리 활성화 경로 제외 |
| `memory-settings.json` | DB 초기화와 런타임에서 공유하는 비밀 없는 메모리 설정 |
| `agent-monitor.json` | Companion의 프로파일·테넌시·사용자·리전·구획·터널 연결 |
| `deployment-target.json` | VM·ADB 식별자와 IP; 원격 배포 단계 입력 |

설정의 리전·구획과 인프라 출력이 다르면 생성하지 않습니다. namespace·저장소 ID·임베딩 모델 또는 차원을 기존 저장소에서 변경하면 기존 기억이 보이지 않거나 임베딩이 호환되지 않을 수 있습니다. 새 저장소로 이관·재임베딩 계획 없이 운영 값을 변경하지 않습니다.

## 메모리 초기화 연결

VM에 `memory-settings.json`을 배치한 후, 관리자·소유자·실행 암호와 TLS DSN을 가진 보호된 초기화 입력을 표준 입력으로 제공합니다. 기존 초기화 입력 키 `admin`, `owner`, `runtime`, `dsn`, `compartment`는 유지합니다.

```sh
python initialize_memory.py \
  --settings /protected/memory-settings.json \
  --output /etc/launchpad-memory.json \
  --service-user launchpad < /protected/adb-setup.json
```

설정의 스키마·실행 계정은 서로 달라야 합니다. 앱은 생성된 런타임 설정에서 임베딩 리전·모델·차원, 스키마·저장소 ID·namespace를 읽습니다. 이전 0.4.0 환경과의 호환을 위해 누락된 선택값에는 기존 기본값을 사용합니다. ADB 없는 환경에서는 이 단계를 실행하지 않습니다.

Companion의 `companion.agent-monitor-config`에 생성한 `agent-monitor.json` 경로를 지정합니다. 토큰 파일은 별도로 보호해 제공하고 SSH 터널을 열어야 합니다. 설정 생성기가 자격증명을 복사하거나 터널을 자동 실행하지는 않습니다.

## 현재 검증과 남은 단계

설정 경계 테스트 5개, 앱 테스트 14개, Terraform 모의 테스트 3개를 통과했습니다. 기존 예제 ID로 만든 별도 바인딩 스냅샷을 사용해 설정 생성도 확인했습니다. 이 스냅샷은 실제 Terraform 적용 결과가 아닙니다.

아직 새 고객 환경을 처음부터 끝까지 자동 배포한 결과는 아닙니다. 기존 예제 설치 스크립트의 릴리스 경로·서비스 이름, 실제 DevOps 배포 실행·롤백, Vault 자격증명 주입을 이 설정에 이어 붙여야 합니다. 새 Terraform 자원 생성과 기존 리소스 import는 수행하지 않았습니다. 런타임 설정 변수화 코드는 로컬 검증 상태이며 현재 OCI의 0.4.0 바이너리는 기존 버전입니다.

설치한 앱의 버전 전환과 실패 복구는 [릴리스 배포·복구](RELEASES.md)를 참고하세요. 서비스명·경로·포트·허용 버전은 별도 릴리스 설정으로 지정합니다.
