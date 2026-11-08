# Launchpad를 OCI Functions에서 빌드하기

Companion에서 비공개 Launchpad 소스를 선택하고, Function 내부에서 python-foundation과 앱을 빌드·테스트하도록 준비하는 경로다. 기존 VM 배포와 OKE 배포를 위한 산출물 검증은 이후 단계이며 현재 Functions 실배포 성공을 의미하지 않는다.

## 소스 준비 설계

`package_function_sources.py`는 두 저장소의 명시한 Git 커밋에서 필요한 파일만 추출한다. 실행 중 작업 폴더의 수정 파일·환경 변수·OCI 설정을 복사하지 않는다. 번들에는 project/의 앱, project/dependencies/foundation/의 내부 라이브러리, source.json의 두 커밋이 들어간다. 앱 버전과 foundation 의존성 버전을 대조한다.

공개 패키지는 앱의 requirements-memory.lock과 deploy/function-build-tools.lock을 합쳐 requirements-build.lock으로 고정한다. 중복 버전 충돌은 실패한다. build-local.json은 내부 foundation 소스의 상대 경로·패키지 이름·버전을 지정한다. Companion의 Python Function은 공개 의존성 → 내부 소스 → 앱 → pip check → 테스트 → 두 wheel 순으로 실행한다.

## 완료 기준과 남은 작업

소스 번들의 해시·커밋·입력 검증이 첫 단계다. 다음은 Linux 대상 의존성 다운로드 크기와 압축 해제 크기, 소스·가상환경·빌드 중간 파일·로그·예비 공간을 포함한 용량 산정이다. 실제 Function probe 값에 맞지 않으면 실행을 강행하지 않는다. 빌더 이미지 제작은 Function 실행 환경을 준비하는 작업이고, 사용자 Python 소스 빌드는 Function에서 수행한다.

이후 버전 관리된 비공개 Object Storage 입력, 제한된 Resource Principal 읽기 권한, Python 전용 Function 이미지 및 필수 환경 설정을 준비한다. Companion에서 실행한 최종 결과가 SUCCEEDED이고 foundation·앱 wheel의 크기·SHA-256이 내려받은 결과와 일치해야 완료로 판단한다. Function wheel 성공을 VM/OKE 배포 성공으로 보지 않는다.
