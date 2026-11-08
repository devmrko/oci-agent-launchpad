# 설치와 배포 전에 필요한 용량 계산하기

OCI 엔지니어가 기본 스택을 설치하고 업데이트·복구까지 수행할 공간을 먼저 확보하도록 하는 설계와 검사 도구다. 파일시스템 크기는 설치 완료 크기만으로 정하지 않는다. **2026-11-08 현재 Terraform과 컨테이너 준비 단계에 연결했으며 Companion UI 연결은 아직 없다.**

## 이번 확인에서 배운 점

앱 VM의 루트 파일시스템은 약 30G, 사용량 22G, 여유 8.1G였다. 이는 관측값이며 디스크 부족으로 빌드가 실패했다는 기록은 아니다. Langfuse 검증 서버에 약 89G가 남았다는 사실만으로 빌드를 함께 실행해도 된다고 판단할 수 없다. 기존 DB·수집 워커의 CPU·메모리·디스크 I/O 및 데이터 증가까지 고려해야 한다. 해당 서버에서는 Python 기본 이미지만 내려받았고 앱 컨테이너 빌드는 아직 하지 않았다.

프로비저닝 전에 역할을 나눈다. 앱 VM에는 런타임과 복구용 릴리스, 빌드 러너에는 소스·다운로드·wheelhouse·테스트 가상환경·이미지 레이어, 관측 서버에는 PostgreSQL·Redis·ClickHouse·수집 버퍼와 보관 데이터를 계산한다. 외부 관리형 DB를 사용하면 그 데이터 용량은 해당 서비스에 별도 산정한다. 로컬 사용량과 중복 합산하지 않는다.

## 산정 계약

파일시스템별로 다음 세 종류를 합산하고 여유분을 더한다. 경로가 달라도 같은 파일시스템이면 한 번에 합산한다.

- `resident`: 작업 시작 때 이미 존재하는 OS·기본 스택·기존 이미지·현재 데이터.
- `growth`: 이번 설치와 보관 기간 동안 늘어날 데이터·로그·이미지·이전 릴리스. 이미 존재하는 크기는 resident에만 넣는다.
- `transient`: 동시에 존재할 다운로드·압축 해제·복사·테스트 환경·빌드 캐시·교체 중 새 Pod의 최대 작업 공간.

`총 필요량 = resident + growth + transient + reserve`다. 기존 서버에서 새 작업을 시작할 때는 `실제 여유 공간 >= growth + transient + reserve`도 만족해야 한다. 동시 빌드 수와 이전 버전 개수는 `copies`에 반영한다. 압축 파일 크기를 설치 크기로 간주하지 않는다. 공유 레이어 절감은 측정 근거가 있을 때만 차감한다.

각 항목에는 실측 또는 추정 근거를 필수로 기록한다. 모든 환경에 동일한 50GB/100GB를 권장하는 기본값은 두지 않는다. 추정은 첫 빌드 전 예산일 뿐이며 실제 peak 사용량과 비교해 갱신한다. GB/GiB 및 OS 예약 영역 차이가 있으므로 OCI 볼륨 할당값과 실제 파일시스템 용량도 대조한다. 볼륨만 늘리고 파티션·파일시스템을 확장하지 않으면 통과로 보지 않는다.

## 계산과 사전 검사

입력 예시는 **계산 설명용 가상 수치이며 운영 권장값이 아니다.**

```json
{
  "schema_version": 1,
  "role": "isolated-build-runner",
  "reserve_gib": 5,
  "components": [
    {"name": "os-and-tools", "phase": "resident", "gib": 10, "copies": 1, "basis": "설명용 가정"},
    {"name": "retained-images", "phase": "growth", "gib": 4, "copies": 2, "basis": "설명용 가정: 두 버전"},
    {"name": "concurrent-workspaces", "phase": "transient", "gib": 6, "copies": 2, "basis": "설명용 가정: 두 빌드 동시 실행"}
  ]
}
```

```sh
python deploy/capacity_plan.py --plan /protected/build-capacity.json
# 실제 작업을 수행할 서버에서 해당 파일시스템의 기존 경로로 확인
python deploy/capacity_plan.py --plan /protected/build-capacity.json --path /var/lib/docker
```

예시 결과는 총 35GiB, 작업 전 여유 최소 25GiB다. 부족하면 `INSUFFICIENT`와 종료 코드 1을 반환한다. 입력 누락·음수·NaN·근거 없는 항목도 거부한다. 검사 도구는 삭제·자동 확장·프로비저닝을 수행하지 않는다. 다른 동시 작업이 공간을 소모할 수 있으므로 실제 러너의 동시성 제한과 함께 사용해야 한다.

## 다음 연결 작업

1. Terraform 적용 전 계획 총량을 boot/data volume 입력에 반영하고 부족한 값을 거부한다. root Terraform의 runtime_capacity_plan은 필수이며, 산정 하한보다 작은 boot_volume_gb를 계획 단계에서 거부한다. VM은 검사 자원에 의존한다.
2. 빌드 시작 전 작업 디렉터리·Docker data root·임시 디렉터리의 실제 마운트를 확인하고 같은 장치는 합산한다. CPU·RAM 사용 예산과 동시성도 별도 점검한다. 이 CLI는 디스크 계산만 수행한다.
3. OKE는 노드 OS·container runtime·이미지 보관·업데이트 중 추가 Pod 공간을 노드별로 산정한다. Pod의 ephemeral-storage requests/limits와 PVC의 데이터 용량은 분리한다. PVC를 늘려도 이미지 레이어 공간은 늘지 않는다.
4. 로그·이미지·이전 릴리스 보관 정책을 명시하고, 복구용 버전을 무작정 삭제해 공간을 맞추지 않는다. 용량·inode·I/O·메모리 경보를 별도로 구성한다.
5. Companion은 필수값, 산정 근거, 부족한 자원과 확장 방법을 표시하는 범용 사전 점검으로 연결한다. 현재는 계획이며 자동 적용 기능으로 표시하지 않는다.

기존 관측 서버에서 앱 빌드를 실행하는 작업은 이 공존 예산 확인 전까지 진행하지 않는다. 이후에는 전용 OCI DevOps 빌드 러너를 우선 사용한다. [OKE 설계](OKE-DESIGN.md)와 [컨테이너 Dockerfile](container/Dockerfile)을 함께 참고한다.

## 실제 실행 경로에 연결된 검사

root Terraform에는 위 JSON을 `runtime_capacity_plan` 키 아래 넣은 tfvars를 제공한다. 기존 환경도 다음 계획부터 이 입력이 필요하며, 누락 시 자동으로 임의 예산을 채우지 않는다. 비대화형 실행은 `-input=false`로 누락을 즉시 확인한다. 총 GiB 예산을 보수적으로 decimal GB로 변환해 boot_volume_gb와 대조한다. OCI 플랫폼 이미지의 최소 크기와 실제 게스트 파일시스템 크기는 별도 확인한다. 이번 변경으로 기존 볼륨을 실제 확장하거나 클라우드 자원을 생성하지 않았다.

컨테이너 준비 도구도 용량 계획을 필수로 받는다. 출력 디렉터리가 생길 파일시스템을 검사한 뒤 ZIP을 풀며, 계획이 실제 ZIP 비압축 크기와 여유분보다 작아도 거부한다. 이 검사는 컨텍스트 추출 공간에 대한 것이며 다른 서버의 Docker data root나 빌드 실행 공간 검사를 대신하지 않는다.

```sh
python deploy/prepare_container.py \
  --result /protected/verified-release \
  --output /work/new-container-context \
  --base-image 'docker.io/library/python@sha256:<검증한-64자리-digest>' \
  --capacity-plan /protected/context-capacity.json
```

Python 관련 검사 22개와 Terraform mock 계획 검사 6개가 통과했다. 실제 공간 부족을 테스트 대역으로 공급했을 때 출력 디렉터리가 만들어지지 않는 것도 확인했다. 실제 디스크를 가득 채우는 시험이나 컨테이너 빌드의 최고 사용량 실측은 하지 않았다. Companion 표시·OKE 노드 자원 연결은 남은 작업이다. Docker 빌드 사전 검사는 아래 제한된 실행 경로에 연결했다.

기존 `deploy/provision_demo.py` SDK 경로도 같은 `runtime_capacity_plan`과 명시적인 정수 `boot_volume_gb`를 요구한다. 고정 50GB 할당을 제거했으며 잘못된 입력에서는 OCI 프로파일 조회·클라이언트 생성·리소스 생성 전에 실패한다. 기존 VM의 실제 볼륨을 자동으로 확장하지는 않는다. 이 실패 순서는 스크립트 전체 진입 테스트로 확인했다.

## Docker 빌드 전 파일시스템 합산 검사

`build_capacity.py`는 `storage` 배열의 각 `{ "path": "<실제 기존 디렉터리>", "plan": <앞의 용량 계획> }`을 받는다. 경로의 실제 장치 ID로 묶어 growth·transient를 합산한다. 같은 장치의 OS 등 resident 항목은 입력에서 한 번만 계산하며, 여유분은 해당 장치 계획 중 최대값을 적용한다. 서로 다른 장치에 빈 공간이 있어도 부족한 장치를 대신하지 않는다.

```sh
python deploy/build_capacity.py --config /protected/build-storage.json
python deploy/build_container.py \
  --context /work/prepared-context \
  --capacity-config /protected/build-storage.json \
  --tag launchpad-service-desk:0.6.0-test
```

빌드 래퍼는 실제 Linux Docker 호스트에서만 사용한다. 고정 로컬 소켓으로 DockerRootDir을 조회하고, 계획에 DockerRootDir 및 컨텍스트 경로가 포함됐는지 검사한다. 기존 default buildx의 docker 드라이버만 지원하며 원격 builder·Docker Desktop·별도 containerd 이미지 저장소는 지원하지 않고 거부한다. 환경변수로 선택한 다른 Docker 호스트나 builder를 계승하지 않는다. 검사를 통과한 경우에만 digest로 고정된 기본 이미지와 linux/amd64 대상으로 buildx build --load를 실행한다. Registry push나 OCI 배포는 수행하지 않는다.

계획에는 빌드 중 컨텍스트 전송 복사본, 이미지 압축 해제, 설치 가상환경 및 레이어, 보관 이미지가 동시에 존재할 공간을 포함해야 한다. 생성된 컨텍스트는 신뢰하는 빌드 입력으로 취급하며, 이 래퍼가 임의 Dockerfile을 안전하게 만드는 것은 아니다. 사용량 검사와 빌드 사이의 외부 작업을 예약·차단하지 않으므로 전용 러너와 동시성 제한이 필요하다. CPU·RAM·inode·I/O 검사는 별도다.

2026-11-08 관련 테스트 18개가 통과했다. 동일 디스크의 개별 예산은 통과하지만 합계가 부족한 경우, 부족 시 Docker build 미호출, 정상 경로의 고정 endpoint·digest 전달을 검증했다. Docker 명령은 테스트 대역을 사용했으므로 이미지 빌드 성공을 뜻하지 않는다. 실제 기존 Langfuse 서버는 DockerRootDir=/var/lib/docker, overlayfs, io.containerd.snapshotter.v1로 확인됐고 buildx 명령도 없었다. 이 서버에서 앱 빌드는 실행하지 않았다. 다음 실측은 저장 구조와 예산을 확인한 전용 OCI DevOps 러너에서 수행한다.
