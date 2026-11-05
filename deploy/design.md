# 첫 OCI 예제 배포 설계

사용자는 2026-11-05 서울 리전, Joungmin.Ko 구획, 새 VM 생성을 지정했습니다. 이 문서는 그 범위의 합성 예제 배포 설계이며 플랫폼 전체의 운영 완료를 의미하지 않습니다.

전용 VCN·서브넷·라우팅·보안 목록을 사용해 기존 업무 네트워크 변경을 피합니다. 최종 VM은 Oracle Linux 9.8, E5 Flex 1 OCPU/8GB, 부트 디스크 50GB입니다. 외부 패키지 설치를 위한 공인 IP를 할당하되 인바운드는 배포 작업자의 현재 IP에서 SSH 22만 허용합니다. 앱은 루프백 8092에서 수신하고 SSH 터널로 확인합니다. VM·부트 디스크 비용은 실행 기간에 따라 발생합니다.

Foundation 고정 커밋과 앱 소스를 비밀정보 없이 전송하고 VM의 Python 가상환경에 설치합니다. 전용 systemd 사용자와 데이터 경로를 사용합니다. 인증 토큰은 VM에서 생성하고 로컬·원격 Git 제외 경로에만 둡니다. OCI API 개인키나 GitHub 토큰을 VM에 복사하지 않습니다.

검증은 VM RUNNING, cloud-init 종료, systemd active, health, 승인·중복 방지·추적 HTTP 흐름, 원격 pytest입니다. 최초 Ubuntu 시험 VM은 DevOps 지원 OS와 맞지 않아 Oracle Linux로 교정합니다. Companion에서는 서울·지정 구획의 VM 조회 및 검사 가능 여부를 확인합니다. 새 Companion의 미구현 배포 실행·모니터링과 SSH 직접 배포를 구분해 기록합니다.

자원 이름은 oci-agent-launchpad-demo 접두사입니다. 생성마다 식별자를 .run에 기록하고 재실행은 기존 자원을 확인합니다. 종료는 사용자 요청 시 VM과 관련 네트워크·부트 디스크를 함께 확인하여 진행합니다. 자동 종료 시점은 아직 지정되지 않았습니다.
