# 첫 OCI 예제 배포 설계

사용자는 2026-11-05 서울 리전, Joungmin.Ko 구획, 새 VM 생성을 지정했습니다. 이 문서는 그 범위의 합성 예제 배포 설계이며 플랫폼 전체의 운영 완료를 의미하지 않습니다.

전용 VCN·서브넷·라우팅·보안 목록을 사용해 기존 업무 네트워크 변경을 피합니다. 최종 VM은 Oracle Linux 9.8, E5 Flex 1 OCPU/8GB, 부트 디스크 50GB입니다. 외부 패키지 설치를 위한 공인 IP를 할당하되 인바운드는 배포 작업자의 현재 IP에서 SSH 22만 허용합니다. 앱은 루프백 8092에서 수신하고 SSH 터널로 확인합니다. VM·부트 디스크 비용은 실행 기간에 따라 발생합니다.

Foundation 고정 커밋과 앱 소스를 비밀정보 없이 전송하고 VM의 Python 가상환경에 설치합니다. 전용 systemd 사용자와 데이터 경로를 사용합니다. 인증 토큰은 VM에서 생성하고 로컬·원격 Git 제외 경로에만 둡니다. OCI API 개인키나 GitHub 토큰을 VM에 복사하지 않습니다.

검증은 VM RUNNING, cloud-init 종료, systemd active, health, 승인·중복 방지·추적 HTTP 흐름, 원격 pytest입니다. 최초 Ubuntu 시험 VM은 DevOps 지원 OS와 맞지 않아 Oracle Linux로 교정합니다. Companion에서는 서울·지정 구획의 VM 조회 및 검사 가능 여부를 확인합니다. 새 Companion의 미구현 배포 실행·모니터링과 SSH 직접 배포를 구분해 기록합니다.

자원 이름은 oci-agent-launchpad-demo 접두사입니다. 생성마다 식별자를 .run에 기록하고 재실행은 기존 자원을 확인합니다. 종료는 사용자 요청 시 VM과 관련 네트워크·부트 디스크를 함께 확인하여 진행합니다. 자동 종료 시점은 아직 지정되지 않았습니다.

## 실제 모델 연결과 공통 실행 계층

2026-11-05 후속 구현. 서울의 Flash Lite·Flash는 ACTIVE 목록과 달리 실제 호출에서 공급자 모델 접근 오류가 발생했습니다. 합성 질문만 애슈번 Flash Lite로 보내는 경로는 실제 성공했습니다. VM·상태 저장은 서울에 유지하며 모델 리전을 명시적으로 설정합니다. 실제 고객 데이터의 국외 전송을 승인한 것으로 확대하지 않습니다.

새 VM 한 개만 포함하는 동적 그룹에 해당 구획의 generative-ai-chat 사용 권한을 부여하고 target.model.id를 google.gemini-2.5-flash-lite로 제한합니다. 개인 API 키를 VM으로 복사하지 않습니다. 기존 정책을 수정하거나 광범위한 권한을 부여하지 않습니다.

Foundation 0.1.1의 공통 Gateway가 도구 입력·호출 예산·권한·자원 정책·실행 이벤트를 처리합니다. 예제는 업무 도구와 모델 프롬프트를 제공합니다. 모델은 검색 또는 초안 생성만 선택할 수 있고 실제 접수는 별도 사용자 승인 API에서만 수행합니다. 실제 모델 토큰·지연·리전과 도구 단계를 하나의 실행 기록으로 연결합니다.

동적 그룹 생성은 테넌시 DynamicResourceGroups 개수 한도로 실패했습니다. 기존 그룹을 수정하지 않고 정책의 request.principal.id 조건에 새 VM OCID를 직접 지정하는 방식으로 교정합니다. 대상 VM·구획·모델의 권한 범위는 동일하며 조건 없는 any-user 권한을 만들지 않습니다.

## 변수 기반 릴리스 전환

배포 운영자는 환경별 JSON에서 systemd 서비스명, 릴리스 루트, 포트와 허용 릴리스(디렉터리·기대 버전)를 지정한다. 릴리스 패키지는 먼저 설치하고, 전환 도구는 설치된 릴리스만 활성화한다. 소스 업로드/패키지 설치와 활성화는 별도 단계다.

root가 소유한 설정과 릴리스만 실행하며, root 소유 systemd drop-in으로 ExecStart를 교체한다. 동시 전환은 파일 잠금으로 차단한다. health의 UP 및 기대 버전이 제한 시간 내 확인되지 않거나 재시작이 실패하면 기존 drop-in을 복원하고 기존 서비스가 회복됐는지 확인한다. ADB·SQLite·환경 비밀값은 수정하지 않는다. 사용자는 이전 릴리스 별칭을 지정해 수동 복구도 수행할 수 있다.

DevOps 배포 명세는 이 도구의 고정 경로와 검증한 릴리스 별칭만 호출한다. sudo 권한은 허용된 별칭별 명령으로 제한한다. 이 단계는 준비된 패키지 활성화이며 Artifact Registry 전송이나 Companion UI 연동 완료를 의미하지 않는다.

## Artifact Registry 패키지 설치

2026-11-06 후속 설계. Linux x86_64/Python 3.12용 wheel과 고정 requirements를 ZIP으로 묶어 불변 Artifact Registry에 올린다. Terraform은 레지스트리·파일 업로드·DevOps 아티팩트/단계/파이프라인·정확한 principal 조건의 전용 IAM을 관리하며 기존 프로젝트·VM을 입력받고 전용 배포 환경을 생성한다. 기존 VM·ADB는 import/apply 대상으로 만들지 않는다.

DevOps가 ZIP을 스테이징 경로에 풀어 놓으면 root 전용 설치 도구가 설정에 고정된 manifest SHA-256을 확인한다. 각 파일을 symlink 없이 제한 크기로 root 소유 위치에 복사하며 SHA-256을 확인한다. 검증한 wheel만 오프라인 설치하고 pip check 및 앱 import를 마친 뒤 기존 활성화 도구로 전환한다. 설치 실패 시 새 디렉터리만 정리하고 실행 중 서비스는 건드리지 않는다. 상태 확인 실패 시 기존 활성화 도구가 직전 버전을 복구한다.

기존 VM의 도구·허용 manifest 설정 갱신은 관리자 bootstrap 단계다. IAM·패키지는 Terraform으로 관리하지만 비밀번호·ADB schema 초기화는 이 상태 파일에 포함하지 않는다. 새 VM 전체 초기화와 무중단 배포는 별도 범위다.

## 새 VM 첫 부팅과 비밀값 연결

새 VM은 cloud-init으로 Python 3.12와 bootstrap용 OCI SDK를 설치하고, 소스에 포함된 표준 라이브러리 기반 설치 도구와 비밀값 없는 설정을 배치한다. Instance Principal로 고정 Artifact Registry 파일과 지정 Vault secret 하나를 읽어 최초 앱을 설치한다. 패키지/파일 체크섬을 기존 설치 도구로 검증하고 전용 서비스 사용자·로컬 데모 토큰·systemd를 구성한다. 신규 서비스 첫 실행 실패는 중지로 처리하며, 기존 서비스 자동 덮어쓰기는 거부한다.

ADB ADMIN/owner 자격은 운영자 초기화 도구의 stdin으로만 전달하고 VM IAM에는 ADMIN secret 접근을 주지 않는다. 초기화 결과 중 앱 user/password/DSN/메모리 설정만 Vault에 게시한다. 비밀값은 Terraform 변수·상태·cloud-init·소스에 포함하지 않는다. 새 VM 정책은 정확한 VM principal과 지정 secret OCID로 제한한다. ADB ACL 추가는 기존 허용 주소를 유지하고 신규 VM 주소만 더한다.

검증은 별도 새 VM에서 cloud-init 완료, 첫 health, Vault 읽기, ADB 메모리 저장·조회와 재부팅 후 데이터 유지까지 확인한다. 기존 실행 VM과 ADB 데이터는 유지한다.


2026-11-06 실제 검증에서 테넌시의 legacy IMDS 차단 정책을 확인했다. Terraform과 SDK 생성 요청 모두 IMDSv2 전용을 명시한다. 부팅 설치 코드는 실행 파일만 umask 022로 생성하고 비밀값 생성은 077로 복귀한다. OCI 다운로드는 응답의 raw 스트림을 읽는다. 최초 user_data 편집으로 기존 VM을 교체하지 않도록 해당 필드만 ignore_changes로 처리하며, 부팅 도구 관리자 갱신과 일반 앱 릴리스 배포를 구분한다. 새 VM에서 수정 후 실제 모델·메모리·재부팅 보존 검증을 통과했다. 자세한 범위는 bootstrap-runtime.md에 기록한다.

## 동작하는 뼈대: 고정 소스 빌드 계약

2026-11-06. 첫 구현 단위는 Companion과 독립적으로 실행할 수 있는 소스/패키지 빌드 도구다. 기존 커밋 하드코딩을 제거하고 Launchpad·Foundation의 Git revision을 필수 입력받는다. revision은 실제 commit SHA로 해석하고, 작업 트리의 미커밋 파일은 포함하지 않는다. 소스 번들에는 허용한 소스·테스트·배포 도구만 포함하며 비밀값·Git 인증 설정을 넣지 않는다. symlink/submodule 입력은 거부한다. 같은 두 revision으로 만든 소스 번들은 같은 해시를 가져야 한다.

Linux x86_64/Python 3.12 빌드 실행기는 새 임시 공간에서 고정 소스를 추출하고 Foundation/app wheel을 생성한다. 고정된 메모리 의존성 lock으로 wheel을 수집하고 오프라인 설치 및 pip check를 통과시킨 뒤 예제 테스트를 실행한다. 성공한 경우에만 배포 ZIP과 별도 release.json을 생성한다. release.json은 두 소스 commit, 앱/Foundation 버전, 대상 플랫폼, 빌드 ID, ZIP·manifest SHA-256을 연결한다. 실패한 빌드에서 배포 가능한 최종 결과를 만들지 않는다. 기존 서비스나 ADB는 이 빌드 단계에서 접근하지 않는다.

이 단계의 완료 증거는 결정적 소스 패키징, 입력 오류/비밀 경로 배제 검사, Linux 빌드 실제 실행 결과다. OCI Managed Build와 Companion 연결 성공은 별도의 후속 증거로 기록한다. 빌드 도구와 런타임 의존성 버전을 혼동하지 않으며 런타임 lock과 검증된 wheel을 사용한다.
