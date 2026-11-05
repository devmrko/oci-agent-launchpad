# 서울 리전 VM 배포

합성 사내 지원 예제를 새 OCI VM에서 실행하고, Companion이 사용하는 DevOps 배포 환경까지 준비한 기록과 재현 절차입니다.

## 현재 결과

2026-11-05, `ap-seoul-1` / `Joungmin.Ko`에 `oci-agent-launchpad-demo-vm-ol9`를 생성했습니다. Oracle Linux 9.8, E5 Flex 1 OCPU·8GB, 부트 디스크 50GB입니다. VM·디스크 비용이 발생하며 자동 종료 일정은 설정하지 않았습니다.

- 앱 커밋 `8c9efdd`, Foundation `e8798f9397d6391d39d9159a801dfa5ec7908663`를 설치했습니다.
- 원격 Python 3.12에서 테스트 7건 통과, 실제 HTTP 규정 조회·승인·중복 방지·추적 확인이 PASS였습니다.
- systemd 서비스와 Cloud Agent가 active, health가 UP입니다. 서비스 재시작 후 DB 파일의 해시가 같고 health가 회복되는 것을 확인했습니다.
- Compute Instance Run Command, Compute Instance Monitoring, Custom Logs Monitoring 플러그인이 RUNNING입니다. 플러그인 실행은 앱 로그 수집 설정·대시보드 완료를 의미하지 않습니다.
- 전용 DevOps 프로젝트와 같은 이름의 VM 환경 `oci-agent-launchpad-demo`를 등록했고 환경 ACTIVE를 확인했습니다. 알림 토픽은 구독 없이 생성했습니다.
- 최초 Ubuntu 시험 VM은 DevOps 지원 OS 조건과 맞지 않아 Oracle Linux로 교정했으며, 부트 디스크 미보존 종료를 요청한 뒤 VM TERMINATED를 확인했습니다.

이번 앱 설치는 SSH 스크립트로 수행했습니다. Companion을 통해 앱 배포 버튼을 실행한 결과는 아닙니다. Companion 브라우저 조작은 다른 Edge 확장 UI가 열려 있어 중단됐으며, 환경의 ACTIVE는 OCI API에서 확인했습니다. 실제 모델·JWT·Companion 배포 실행·앱 관측 화면은 남아 있습니다.

## 접속과 운영

앱은 VM의 `127.0.0.1:8092`에만 열려 있습니다. 인바운드는 생성 당시 작업자 IP의 SSH 22만 허용합니다. 로컬 SSH 터널이 열려 있는 동안 `http://127.0.0.1:8093/docs`와 `/health`로 접속합니다. Mac 재시작 또는 터널 종료 후에는 다시 연결해야 합니다.

```bash
ssh -i .run/oci-launchpad/id_ed25519 -o IdentitiesOnly=yes \
  -o UserKnownHostsFile=.run/oci-launchpad/known_hosts \
  -N -L 127.0.0.1:8093:127.0.0.1:8092 opc@<VM 공인 IP>
```

현재 IP와 자원 ID는 OCI 또는 Git에서 제외한 `.run/oci-launchpad/state.json`을 이용해 확인합니다. 접속 장소가 바뀌면 허용된 SSH 원본 IP도 검토해야 합니다. SSH 개인키·API 토큰을 문서나 Git에 추가하지 않습니다.

원격 서비스는 `launchpad-demo`, 설치 경로는 `/opt/launchpad/releases/8c9efdd`, 데이터 경로는 `/var/lib/launchpad/desk.db`입니다. `sudo systemctl status launchpad-demo`, `sudo journalctl -u launchpad-demo`로 상태와 서버 로그를 확인합니다. 데모 인증 정보는 root 전용 `/etc/launchpad-demo.env`와 `/var/lib/launchpad/.run/demo-accounts.json`에 있으며 출력·공유하지 않습니다.

## 재현 절차

OCI Python SDK, 기존 인증 프로파일, 해당 구획의 자원 생성 권한과 SSH가 필요합니다. 스크립트는 실제 유료 자원을 생성합니다. 먼저 [설계](design.md)를 읽고 대상·네트워크·사용 기간을 확정합니다.

1. `config.example.json`을 `.run/oci-launchpad/config.json`으로 복사하고 실제 식별자·현재 SSH 원본 IP·공개키 경로를 채웁니다. 이미지가 Oracle Linux 9 x86인지 확인합니다.
2. `python deploy/provision_demo.py --config .run/oci-launchpad/config.json --state .run/oci-launchpad/state.json`으로 생성합니다. 기존 상태 파일을 지우거나 다른 환경에 재사용하지 않습니다.
3. `python deploy/prepare_devops.py`로 예제 전용 프로젝트·VM 환경을 등록합니다. 현재 작업 디렉터리는 저장소 루트여야 합니다.
4. `python deploy/package_sources.py --foundation <고정 Foundation 저장소>`로 소스만 묶습니다. 생성된 archive와 `install_demo.sh`를 새 VM의 `/tmp`로 복사합니다.
5. 원격 `cloud-init status --wait`가 완료되면 `sudo bash /tmp/install_demo.sh /tmp/sources.tar.gz`를 실행합니다. 설치 스크립트는 첫 예제 버전 `8c9efdd` 전용입니다.
6. 원격 앱 디렉터리에서 설치 venv의 `python -m pytest -q -p no:cacheprovider`를 실행합니다. root로 `/var/lib/launchpad`에서 설치된 `scripts/smoke.py`를 실행하면 토큰을 출력하지 않고 실제 HTTP 검증을 합니다.

Linux/Python 3.12 설치에서는 SQLAlchemy가 greenlet 3.5.6을 추가로 선택했습니다. 기존 Mac lock에서 빠진 플랫폼 의존성이므로 이번 배포를 완전한 플랫폼 공통 lock 검증으로 주장하지 않습니다. 다음 배포 산출물은 플랫폼별 lock과 이미지 digest를 고정하는 것이 남은 작업입니다.

종료 시에는 VM·부트 디스크, 전용 VCN·서브넷·라우팅·보안 목록·Internet Gateway, DevOps 환경·프로젝트·알림 토픽을 확인합니다. 기존 고객 자원을 이름이 비슷하다는 이유로 삭제하지 않습니다. 앱 데이터 보존 여부를 결정한 뒤 종료합니다.

지원 OS 근거: [OCI DevOps 인스턴스 그룹 배포](https://docs.oracle.com/en-us/iaas/Content/devops/using/deploy_instancegroups.htm).
