# 설치와 배포 전에 필요한 용량 계산하기

OCI 엔지니어가 기본 스택을 설치하고 업데이트·복구까지 수행할 공간을 먼저 확보하도록 하는 설계와 검사 도구다. 파일시스템 크기는 설치 완료 크기만으로 정하지 않는다. **2026-11-08 현재 계산·사전 검사 CLI 구현 단계이며 Terraform·Companion 자동 연결은 아직 없다.**

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

1. Terraform 적용 전 계획 총량을 boot/data volume 입력에 반영하고 부족한 값을 거부한다. 현재 root Terraform에는 boot_volume_gb 입력이 있지만 이 계산과의 연결은 아직 없다.
2. 빌드 시작 전 작업 디렉터리·Docker data root·임시 디렉터리의 실제 마운트를 확인하고 같은 장치는 합산한다. CPU·RAM 사용 예산과 동시성도 별도 점검한다. 이 CLI는 디스크 계산만 수행한다.
3. OKE는 노드 OS·container runtime·이미지 보관·업데이트 중 추가 Pod 공간을 노드별로 산정한다. Pod의 ephemeral-storage requests/limits와 PVC의 데이터 용량은 분리한다. PVC를 늘려도 이미지 레이어 공간은 늘지 않는다.
4. 로그·이미지·이전 릴리스 보관 정책을 명시하고, 복구용 버전을 무작정 삭제해 공간을 맞추지 않는다. 용량·inode·I/O·메모리 경보를 별도로 구성한다.
5. Companion은 필수값, 산정 근거, 부족한 자원과 확장 방법을 표시하는 범용 사전 점검으로 연결한다. 현재는 계획이며 자동 적용 기능으로 표시하지 않는다.

기존 관측 서버에서 앱 빌드를 실행하는 작업은 이 공존 예산 확인 전까지 진행하지 않는다. 이후에는 전용 OCI DevOps 빌드 러너를 우선 사용한다. [OKE 설계](OKE-DESIGN.md)와 [컨테이너 Dockerfile](container/Dockerfile)을 함께 참고한다.
