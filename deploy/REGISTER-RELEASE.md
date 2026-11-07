# 준비한 릴리스를 VM에 등록하기

운영자가 준비한 릴리스만 설치할 수 있도록 VM 허용 목록을 갱신한다. 기존 복구 버전과 서비스 설정을 보존하며, 앱 설치·재시작·Terraform·IAM 변경은 별도 단계다. Companion은 기존 일반 배포 파이프라인 실행 역할을 유지한다.

## 구현 계약

`register_release.py`는 root 전용이다. 신뢰한 준비 결과의 `preparation.json` SHA256을 별도 인자로 받고 설정 파일 해시를 다시 대조한다. OCI IMDSv2에서 현재 instance ID와 compartment ID를 읽어 준비 대상과 비교한다. 메타데이터 조회 실패 시 변경 없이 종료한다. [OCI 메타데이터 문서](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/gettingmetadata.htm)를 따른다.

기존 설치·활성화와 같은 배포 잠금을 취득한 뒤 현재 VM 설정의 원본 바이트 해시를 준비 당시 해시와 비교한다. 달라졌으면 최신 설정으로 다시 준비한다. 기존 별칭 삭제·수정, 서비스·경로·포트 변경을 거부하고 준비한 별칭 하나만 추가한다. 같은 내용이 이미 등록된 준비 결과는 변경 없이 종료한다.

입력·설정·sudoers와 부모 디렉터리는 root 소유이며 비소유자 쓰기와 심볼릭 링크를 허용하지 않는다. 새 sudoers를 visudo로 검사한 뒤 sudoers, 설정 순으로 교체한다. 일반 예외에는 기존 sudoers를 복원한다. 파일 각각은 원자적으로 교체하지만 두 파일 전체가 전원 장애까지 원자적인 것은 아니다. 중간 강제 종료 시 새 sudoers에만 추가된 별칭은 기존 설정에 없으므로 설치가 거부된다. 설정 교체 전 종료였다면 동일 준비 결과를 다시 실행할 수 있다. 교체 후였다면 최신 설정으로 재준비한다. 외부 root 관리자가 bootstrap이나 수동 편집을 동시에 수행하는 상황은 잠금 보호 범위가 아니다.

완료 기준: 정상 추가·기존 별칭 보존, 변경된 설정·파일 변조·잘못된 VM·기존 항목 수정 거부, 동시 잠금 거부, sudoers 검사 실패 및 설정 쓰기 실패 복원, 실제 VM에서 기존 별칭 재등록 무변경 확인.

## 실행 방식

먼저 [릴리스 입력 준비](PREPARE-RELEASE.md)를 완료한다. 준비 결과 중 `preparation.json`, `deployment.json`, `release.tfvars.json`만 VM의 root 소유 디렉터리(예: `/var/lib/launchpad-registrations/release-050`)로 복사하고 파일 권한을 0600으로 설정한다. 원본 준비 결과에서 확인한 receipt SHA256을 별도로 기록한다. 이 해시는 전자서명이 아니므로 준비 결과와 실행 명령을 전달하는 관리자 경로를 신뢰해야 한다.

등록 스크립트와 `activate_release.py`, `prepare_release.py`, `verify_release.py`는 함께 root 소유 디렉터리에 설치한다. Python 3.11 이상을 사용한다.

```sh
sudo python3.12 /usr/local/lib/launchpad-registration/register_release.py \
  --prepared /var/lib/launchpad-registrations/release-050 \
  --receipt-sha256 '<원본 preparation.json SHA256>'
```

성공 출력은 `REGISTERED` 또는 `UNCHANGED`다. 서비스 상태는 별도로 확인한다. 이후 Terraform 계획·적용 및 필요한 pipeline IAM 갱신을 수행하고 Companion에서 성공 빌드와 연결된 배포를 실행한다.

## 검증 결과와 운영 시 주의점

2026-11-07 등록·준비·패키지 검증·다운로드 관련 테스트 37개가 통과했다. 신규 별칭 추가와 오류 복원은 임시 파일 기반 테스트로 검증했다. 실제 서울 VM에서는 기존 0.5.0 별칭 재등록이 `UNCHANGED`로 종료됐다. 설정·sudoers SHA256과 서비스 PID·시작 시각이 실행 전후 같았고 health는 `UP`, 버전은 `0.5.0`이었다. 실제 VM에 새 별칭을 추가하는 검증은 이번 실행에 포함하지 않았다.

`/var/lib/launchpad`는 앱 계정 소유 데이터 경로여서 그 아래에 root 소유 파일을 두어도 신뢰할 수 있는 관리자 경로가 아니다. 실제 실행에서 이 경로를 거부했다. 기존 데이터 경로의 소유권을 바꾸지 않고 `/var/lib/launchpad-registrations`를 별도로 생성했다. 향후 설치 자동화도 관리자 설정과 앱 쓰기 데이터를 분리해야 한다. 동일 별칭의 무변경 처리는 sudoers 복구 기능이 아니다. 기존 sudoers 손상은 별도 운영 복구로 다룬다.

남은 단계는 새 릴리스의 Terraform 계획·적용, 공유 정책 소유 상태에 새 pipeline을 반영하는 절차의 자동화다. 현재 도구는 클라우드 자원이나 IAM 정책을 변경하지 않는다.
