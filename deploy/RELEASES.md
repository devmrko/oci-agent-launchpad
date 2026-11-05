# 준비된 에이전트 릴리스 배포·복구

운영자는 환경별 설정으로 설치된 앱 버전을 전환하고, 실패하면 직전 버전으로 복구할 수 있습니다. OCI Companion에서 파이프라인을 선택하면 OCI DevOps가 VM의 전환 도구를 실행합니다. 앱의 ADB 메모리와 SQLite 업무 데이터는 그대로 유지합니다.

## 첫 실행

전제: Oracle Linux VM, 실행 중인 정상 서비스, root가 소유한 설치 완료 릴리스, OCI DevOps 프로젝트·Instance Group 환경이 필요합니다. VM의 Compute Instance Run Command가 동작해야 합니다. 이 절차는 패키지를 새 VM에 설치하는 절차가 아닙니다.

1. `release.example.json`을 환경에 맞게 복사합니다. `service`, `release_root`, `port`, `releases`는 필수이며 `health_timeout_seconds`는 선택(기본 45초, 최대 300초)입니다. 별칭마다 실제 디렉터리와 기대 앱 버전을 지정합니다.
2. VM 관리자가 `activate_release.py`를 `/usr/local/sbin/launchpad-activate`에 root:root 755로, 설정을 `/etc/launchpad-deployment.json`에 root:root 600으로 설치합니다. 릴리스와 상위 경로는 다른 사용자에게 쓰기 권한이 없어야 합니다.
3. VM 관리자가 `ocarun`에 필요한 명령만 허용합니다. 예:

```sudoers
ocarun ALL=(root) NOPASSWD: /usr/local/sbin/launchpad-activate memory-0.4.0, /usr/local/sbin/launchpad-activate memory-0.3.0
```

`visudo -cf /etc/sudoers.d/launchpad-deploy`로 검사합니다. root 임의 명령 권한은 필요하지 않습니다.

4. OCI SDK가 설치된 로컬 환경에서 파이프라인을 등록합니다. 아래 식별자는 자신의 환경 값으로 지정합니다. 스크립트는 등록만 하며 실행하지 않습니다.

```sh
python deploy/prepare_release_pipeline.py \
  --profile DEFAULT --region ap-seoul-1 \
  --project-id '<project OCID>' --environment-id '<environment OCID>' \
  --release-config deploy/release.example.json --release memory-0.4.0 \
  --state .run/pipeline-0.4.0.json
```

이전 버전은 별도 `--release`와 `--state`로 등록합니다. 상태 파일은 같은 대상에서 재사용합니다. 배포 명세는 인라인이며 패키지 파일이나 비밀값을 담지 않습니다.

5. 관리자가 배포 파이프라인에 선택 구획의 `read devops-family`, `read instance-family`, `use instance-agent-command-family`, `use ons-topics` 권한을, 대상 VM에는 `use instance-agent-command-execution-family`를 부여합니다. 예제 검증에서는 각각의 정확한 파이프라인/VM OCID를 `request.principal.id` 조건으로 제한한 전용 정책을 사용했습니다. 일반 테넌시에서는 관리자가 승인한 동적 그룹을 사용할 수 있습니다. 이 인라인 활성화 경로는 Secret/Artifact Registry 읽기 권한을 사용하지 않습니다.
6. Companion의 **배포 → 환경 선택 → 준비된 파이프라인 실행·복구** 또는 `/deployments/runs`에서 리전·구획을 확인하고 파이프라인을 선택합니다. 대상 확인 후 실행하고 상태를 새로고침합니다. `SUCCEEDED` 이후 **에이전트 상태 확인**에서 앱 버전을 확인합니다.

## 실패와 복구

전환 도구는 systemd drop-in만 바꾸고 재시작합니다. `/health`가 `UP`이고 기대 버전과 일치해야 성공입니다. 기존 서비스가 이미 비정상이면 전환을 시작하지 않습니다. 재시작 또는 새 버전 상태 확인에 실패하면 원래 drop-in을 복원하고 이전 버전의 정상 응답까지 확인합니다. 복구 실패는 별도의 실패로 보고하므로 운영자 확인이 필요합니다.

수동 복구는 이전 버전 파이프라인 실행입니다. 데이터 스키마가 호환되는 릴리스에만 적용하세요. DB 마이그레이션 되돌리기, VM 장애 시 복구, 무중단 전환, 프로세스 강제 종료 시 자동 복구는 이 도구의 보장 범위에 포함되지 않습니다.

## 검증 범위

2026-11-06 서울 예제 VM에서 직접 호출로 0.4.0 → 0.3.0 → 0.4.0과 각 health 버전을 확인했습니다. OCI DevOps의 0.4.0 실행도 `SUCCEEDED`로 완료됐습니다. Companion 화면에서 시작한 0.3.0 복구와 0.4.0 재배포도 모두 OCI `SUCCEEDED`로 확인했습니다. 복구 후 0.3.0은 Companion 화면, 최종 0.4.0은 VM health로 확인했습니다. 로컬 테스트는 새 릴리스 상태 확인 실패, 재시작 실패, 복구 실패, 잘못된 별칭과 비정상 기존 서비스를 검증합니다.

현재는 미리 설치한 릴리스를 활성화합니다. Artifact Registry에서 패키지 다운로드·검증·설치, Terraform으로 DevOps/IAM/VM 초기화 전체 구성, 다중 VM 및 무중단 배포는 후속 작업입니다. 기존 `install_memory.sh`는 최초 수동 설치용 고정 버전 스크립트이므로 이 활성화 경로와 구분합니다.

공식 근거: [OCI 배포 명세](https://docs.oracle.com/en-us/iaas/Content/devops/using/deployment_specs.htm), [DevOps IAM 정책](https://docs.oracle.com/en-us/iaas/Content/devops/using/devops_iampolicies.htm).
