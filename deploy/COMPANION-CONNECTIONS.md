# 환경 값으로 여러 앱의 Companion 연결 준비하기

VM·OKE의 여러 에이전트를 등록할 때 같은 scope·OCID·경로를 반복 입력하는 일을 줄인다. 현재 Companion의 앱/인증 참조/OKE 조회 레지스트리 3개를 한 설정에서 생성한다. 앱 실행에는 Companion이 필요하지 않다.

## 입력

`companion-connections.example.json`은 VM와 OKE 두 앱의 예시다. `<...>`는 실제 값으로 교체해야 한다. 토큰·DB 암호·kubeconfig 내용을 입력하지 않고 파일 경로만 지정한다.

| 값 | 필수/선택 | 의미 |
|---|---|---|
| scope | 필수 | profile/tenancy/user/region/compartment. 실제 Companion 연결과 일치해야 함 |
| apps[].key | 필수 | scope 내 고유한 앱 식별 키. ID 재생성 기준이므로 유지 |
| id | 선택 | 기존 앱 등록 UUID를 유지할 때 지정 |
| name/environment | 필수 | 표시 이름·실행 환경 |
| baseUrl | 필수 | 현재 Companion의 HTTP loopback health 터널 주소 |
| tokenFile | 필수 | Companion 서버에서 읽을 보호된 토큰 파일의 절대 경로 |
| dependencies | 선택 | VM/ADB/OKE 유형·표시 이름·OCID, 앱당 최대 8개 |
| oke | 선택 | OKE clusterId·kubeconfig 절대 경로·namespace·deployment |
| oke.server/tlsServerName | 선택 | 사설 API 터널의 HTTPS 주소·원래 인증서 검증 호스트 |
| oke.inspectNodes | 선택 | 기본 false. true이면 앱 할당 노드 조회; 별도 nodes get 권한 필요 |

프로파일/주체/리전/구획 또는 key가 바뀌면 자동 ID도 달라진다. 단순 표시 이름 변경은 ID를 바꾸지 않는다. 다른 scope로 기존 ID를 옮겨 접근 권한이 생기는 것은 아니다. 형식 검증은 실제 OCI 접근·구획·kubeconfig 인증 일치 검증을 대신하지 않는다.

## 생성과 실행

```sh
python deploy/render_companion_connections.py \
  --config /protected/customer-connections.json \
  --output /protected/new-companion-bundle
```

새 폴더에만 생성한다. 기존 폴더·심볼릭 링크를 덮어쓰지 않는다. 출력 폴더 0700, 파일 0600이다. 출력에는 비밀값이 없지만 사용자/리소스 식별자와 로컬 경로가 있으므로 공개 저장소에 올리지 않는다.

독립 Companion 인스턴스를 다음 옵션으로 시작한다. 기존 레지스트리에 자동 병합하지 않으므로 현재 운영 인스턴스의 설정 위에 복사하지 않는다.

```sh
./scripts/run.sh \
  --companion.agent-connections=/protected/new-companion-bundle/agent-connections.json \
  --companion.agent-credentials=/protected/new-companion-bundle/agent-credentials.json \
  --companion.oke-workloads=/protected/new-companion-bundle/oke-workloads.json \
  --companion.kubectl=/absolute/path/to/kubectl
```

이 시작 명령은 Companion 저장소에서 실행한다. kubectl·OCI CLI·신뢰한 kubeconfig, 토큰 파일과 사설 연결은 관리자가 준비해야 한다. 생성기는 그 파일을 읽거나 생성하지 않는다. Companion 화면에서 scope·앱 선택 후 health/OCI/Pod/노드 결과를 확인한다. 노드 조회는 선택 기능이며 실패해도 Pod 결과를 유지한다.

## 검증 범위

생성기 테스트는 두 앱의 ID·인증·OKE 연결 계약, ID 안정성, 타입/주소/경로/중복/미정값 거부, 파일 권한·기존 폴더 보존을 확인한다. 새 고객 인프라 생성·메모리 초기화·빌드·배포·상시 연결을 이 생성기가 완성하는 것은 아니다. 전체 순서는 [준비 상태 점검](../docs/design/platform-readiness-review.md)을 따른다.

2026-11-09 검증: 관련 Python 테스트 30건(하위 사례 10건 포함 별도 집계) 통과. 생성된 합성 파일을 실제 Companion Java 코드로 읽는 `CompanionBundleContractTest` 1건도 통과했다. 생성기만의 자체 필드 비교에 그치지 않고 소비 측 역직렬화와 scope 경계를 대조했다.
