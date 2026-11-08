# Launchpad를 OCI Functions에서 빌드하기

Companion에서 비공개 Launchpad 소스를 선택하고, Function 내부에서 python-foundation과 앱을 빌드·테스트하도록 준비하는 경로다. 기존 VM 배포와 OKE 배포를 위한 산출물 검증은 이후 단계이며 현재 Functions 실배포 성공을 의미하지 않는다.

## 소스 준비 설계

`package_function_sources.py`는 두 저장소의 명시한 Git 커밋에서 필요한 파일만 추출한다. 실행 중 작업 폴더의 수정 파일·환경 변수·OCI 설정을 복사하지 않는다. 번들에는 project/의 앱, project/dependencies/foundation/의 내부 라이브러리, source.json의 두 커밋이 들어간다. 앱 버전과 foundation 의존성 버전을 대조한다.

공개 패키지는 앱의 requirements-memory.lock과 deploy/function-build-tools.lock을 합쳐 requirements-build.lock으로 고정한다. 중복 버전 충돌은 실패한다. build-local.json은 내부 foundation 소스의 상대 경로·패키지 이름·버전을 지정한다. Companion의 Python Function은 공개 의존성 → 내부 소스 → 앱 → pip check → 테스트 → 두 wheel 순으로 실행한다.

## 완료 기준과 남은 작업

소스 번들의 해시·커밋·입력 검증이 첫 단계다. 다음은 Linux 대상 의존성 다운로드 크기와 압축 해제 크기, 소스·가상환경·빌드 중간 파일·로그·예비 공간을 포함한 용량 산정이다. 실제 Function probe 값에 맞지 않으면 실행을 강행하지 않는다. 빌더 이미지 제작은 Function 실행 환경을 준비하는 작업이고, 사용자 Python 소스 빌드는 Function에서 수행한다.

이후 버전 관리된 비공개 Object Storage 입력, 제한된 Resource Principal 읽기 권한, Python 전용 Function 이미지 및 필수 환경 설정을 준비한다. Companion에서 실행한 최종 결과가 SUCCEEDED이고 foundation·앱 wheel의 크기·SHA-256이 내려받은 결과와 일치해야 완료로 판단한다. Function wheel 성공을 VM/OKE 배포 성공으로 보지 않는다.

## 2026-11-08 확인 결과

고정된 Launchpad 커밋 59d940936d094d7699f81f3e4a6625d0f6428471과 foundation d207f52281552a551457733bebc0ee62036b36e3으로 번들을 만들었다. 파일 48개, 압축 49,641 bytes, 소스 내용 175,245 bytes다. 번들 SHA-256은 2910395ba35a260cb9c8bf52c302fededcd23815d3c6676e86d9b8faa931d22d다. 번들 도구와 기존 소스 패키징 테스트 9개가 통과했다.

Linux ARM/Python 3.12용 공개 의존성 95개 wheel 다운로드를 완료했다. 압축 크기 합계는 153,223,603 bytes(약 146MiB), ZIP 항목의 비압축 합계는 566,380,779 bytes(약 540MiB)다. 설치 시 생성되는 파일·파일시스템 할당·가상환경·중간 파일·로그는 포함하지 않았다. 따라서 이 합계를 실제 설치 크기나 최고 사용량으로 부르면 안 된다. 이와 별도로 기존 Maven Function의 /tmp 관측값은 768MiB였으며 신규 Python Function은 아직 probe하지 않았다.

현재 경로는 공개 의존성을 python-v1 빌더 이미지에 미리 설치하는 방식이다. Companion의 Dockerfile.dependencies와 BUILD_PREINSTALLED_LOCK 검증을 사용하면 실행별 작업 공간에는 내부 라이브러리와 앱만 설치한다. 테스트·wheel 빌드는 계속 Function에서 수행한다. 다음 작업은 전용 이미지 제작 환경에서 러너 및 의존성 이미지를 만들고, OCI Registry에 올린 뒤 Python 전용 Function을 배포하는 것이다. 이미지 부트스트랩에 Managed Build를 사용하더라도 사용자 소스 빌드를 Managed Build로 바꾸는 것은 아니다.

실행 중 필요한 임시 공간은 새 Function probe와 실제 첫 실행으로 측정해야 한다. 기존 Langfuse 서버의 남는 디스크만을 근거로 이미지 빌드를 함께 실행하지 않는다. 메모리 한도·콜드 스타트·의존성 충돌·IAM 및 실제 결과 업로드 검증은 남아 있다.

소스 준비 명령(이미 존재하는 출력은 덮어쓰지 않음):

```sh
.venv/bin/python deploy/package_function_sources.py \
  --foundation /path/to/python-foundation \
  --foundation-revision <40자리 커밋> \
  --launchpad-revision <40자리 커밋> \
  --output /path/to/new-source-bundle.tgz
```
