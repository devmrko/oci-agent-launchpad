# OCI Agent Launchpad

고객의 아이디어를 OCI에서 운영하는 AI 에이전트로 연결하기 위한 프로젝트입니다.

고객의 업무 문제를 출발점으로 AI 에이전트를 함께 만들고 OCI 배포와 상용 운영으로 연결하기 위한 기획 자료입니다. 대상 독자는 현장 Customer Engineer(CE), 아키텍트, 플랫폼 담당자와 프로그램 책임자입니다.

현재는 **방법론과 동작하는 파일럿** 단계입니다. Python Foundation 예제를 서울 OCI VM에 배포하고 실제 모델 호출, 승인 후 업무 처리, Oracle Agent Memory 저장·검색을 검증했습니다. 기존 VM의 Companion·DevOps 릴리스 배포·복구와 별도 새 VM의 Vault 기반 설치·재부팅 보존까지 확인했습니다. 새 VM 부팅 검증에는 수정본 관리자 배치가 포함됐으며, 전체 AgentCore 기능 동등성이나 운영 준비 완료를 의미하지 않습니다.

AgentCore 대응 플랫폼과 OCI Companion은 독립 프로젝트입니다. 플랫폼은 Companion 없이도 사용할 수 있어야 하며, Companion은 구축·빌드·배포·모니터링을 돕습니다. 실제 플랫폼을 구축하면서 발견한 Companion의 부족한 기능은 해당 프로젝트에 구현합니다.

- [현재 진척도와 다음 완료 기준](docs/status.md)
- [독립 플랫폼과 Companion 연동 범위](docs/companion-agent-platform-review.md): 현재 동작, 관리 화면과 실행 서비스의 책임, 빌드 연결 우선순위입니다.
- [OCI 배포 결과와 접속 절차](deploy/README.md): 새 VM, 원격 검증, Companion 연동 상태입니다.
- [새 VM 첫 실행과 Vault 연결](deploy/bootstrap-runtime.md): 변수, 설치 흐름, 실제 검증 범위와 운영 제약입니다.
- [첫 예제 실행](examples/service-desk/README.md): 규정 조회, 승인 후 접수, 기억과 실행 추적을 확인합니다.
- [상세 고객 양식](templates/use-case.md): 필수·옵션·조건부 입력과 요구·설계·배포·검증 표를 제공합니다.

- [OCI Companion과 Python Foundation 연계 계획](docs/companion-integration-plan.md): 기존 기반을 사용해 앱을 만들고 Companion에서 배포·모니터링하는 목표 흐름입니다.
- [템플릿 요구사항](docs/template-requirements.md): AI-DLC 근거, 상세 템플릿, 필수·옵션 구분과 일반적인 활용 예제에 대한 사용자 요구입니다.
- [고객 공동 개발 프로그램과 파일럿 실행 계획](docs/oci-ai-dlc-plan.md): 녹취에서 도출한 방향, AI-DLC 적용, 고객 준비, 3일 워크숍, 운영 전환과 성과 측정입니다.
- [AgentCore 기능을 OCI에서 대체하는 구성 계획](docs/oci-agent-platform-plan.md): 기능별 대체안, 최소 구성과 운영 확장 구성, 직접 구현할 부분과 검증 과제입니다.

먼저 템플릿 요구사항을 기준으로 AI-DLC 원문과 워크플로의 대응 관계, 상세 양식과 예제 구성을 설계합니다. 프로그램 계획과 대체 구성 계획은 고객 적용 및 OCI 운영을 위한 검토안으로 함께 사용합니다. 기술 선택은 대상 리전과 테넌시의 실제 사용 가능 여부를 확인한 뒤 확정합니다.

작성 기준일: 2026-11-06. 사용자 제공 녹취, AWS AI-DLC 방법론과 공개 저장소, AWS 및 Oracle 공식 문서를 참고했습니다. 이 자료는 Oracle 또는 AWS의 공식 프로그램·제품 로드맵을 의미하지 않습니다.
