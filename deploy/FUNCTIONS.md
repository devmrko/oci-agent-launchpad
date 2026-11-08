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

## 전용 이미지 제작 경로와 IAM 확인

2026-11-08 서울의 launchpad-python-function-image 파이프라인을 만들고 Companion 화면에서 고정 커밋 ae8bf99d3e8871cd062a6b6554dc0795df09a7bc로 실행했다. 사용자 소스 빌드가 아니라 Function 실행 이미지를 처음 만드는 단계다. OCI 비공개 저장소의 python-function-image-060 브랜치에 빌더 코드와 공개 의존성 잠금 파일을 게시했다. GitHub에는 push하지 않았다.

관리형 러너가 x86이므로 Python 전용 Application도 GENERIC_X86으로 준비했다. 공식 Python 3.12 amd64 베이스 digest는 sha256:268cf2b851b1f5480611d8cfee4d036a1a7ee95cf02d3295f36c520e91e14a11로 고정했다. ARM 사전 다운로드 수치는 x86 설치 실측으로 일반화하지 않는다. 용량 사전 검사는 이미지/레이어 4GiB + 설치/중간 파일 4GiB + 전달/내보내기 4GiB + 예비 4GiB의 보수적 예산을 적용한다. 이 예산은 최고 사용량 실측이 아니다. 실제 러너에서 여유 38,802,616,320 bytes, 메모리 한도 7,218,348,032 bytes를 확인하고 검사를 통과했다.

비공개 버킷 launchpad-python-function-sources는 버전 관리를 켰으며 결과는 별도 launchpad-python-function-results에 저장한다. 이미지 게시 대상도 전용 비공개 OCIR 저장소 launchpad/python-function-builder다. 이미지 제작 성공, 전달 성공, 고정 digest 확인 전에는 Function 생성 스크립트가 진행하지 않는다.

IAM 레슨런: devops-artifacts라는 잘못된 리소스 이름으로 정책을 만들면 API가 400 No permissions found로 거부했다. 이를 권한 부족으로 단정해 더 넓은 권한을 부여하지 않았다. [공식 DevOps 정책 문서](https://docs.oracle.com/en-us/iaas/Content/devops/using/devops_iampolicies.htm)를 확인하고 DEVOPS_DEPLOY_ARTIFACT_READ를 명시한 정책으로 생성에 성공했다. 이미지 게시 권한은 해당 build pipeline ID와 target.repo.name으로 제한했다. 정책 생성 성공과 실제 이미지 전달 성공은 별도로 확인해야 한다.

SSH 게시 시에는 기존에 공식 fingerprint와 대조한 scm_known_hosts와 OCI에 등록된 사용자 SSH 키 설정을 사용한다. 일반 git push가 Host key verification failed로 실패했을 때 StrictHostKeyChecking을 끄지 않고 기존 검증 설정을 적용했다.

## 실제 Function 초기화에서 확인한 오류

첫 이미지 060-1은 제작·의존성 검사·import 검사·Registry 전달을 통과했고 digest sha256:364d76d9ff0fe2a673afc9590daa234b5b8e7026a23bbc36b851c1555f2e9fd4로 Function을 생성했다. 하지만 실제 probe는 502 FunctionInvokeContainerInitFail이었다. OCI 호출 로그에서 `[FATAL tini] exec /usr/local/bin/fdk failed: No such file or directory`를 확인했다. import 검사에서는 entrypoint를 python3로 덮어썼으므로 이 오류를 검출하지 못했다.

Companion 커밋 72f3349는 `/usr/bin/env fdk`로 시작 경로를 수정했다. OCI 소스 커밋 e61bbe3ffd53041753ef06640d62747f7fa5e082의 새 이미지 060-2 빌드는 실제 기본 entrypoint를 띄운 뒤 FN_FORMAT=http-stream, FN_LISTENER=unix:/tmp/fdk-smoke.sock로 probe HTTP 요청까지 보내도록 강화했다. 이 기록 시점에는 재빌드 중이며 Function에서의 수정 검증과 Launchpad 소스 빌드는 아직 완료하지 않았다.

호출 로그는 Application 단위 Functions/invoke 서비스 로그로 활성화한다. OCI SDK의 추상 Source에 service/resource/category를 넣으면 TypeError가 발생하므로 OciService 모델을 사용한다. Logging 활성화와 서비스 로그 ACTIVE를 확인한 후 실패 원인을 수집했다. 컨테이너 이미지 검사 성공과 실제 클라우드 시작 성공을 별도 완료 조건으로 유지한다.

두 번째 빌드에서는 기본 entrypoint로 FDK 서버가 시작됐으나 smoke 검사 자체가 `/`를 호출해 404로 실패했다. 사용한 fdk 0.1.128의 공식 패키지 소스에서 POST `/call` 등록을 확인하고 검사 경로를 수정했다. OCI 커밋 68efecad39d70a32b79dd3a5883d78c2f3165193을 지정한 세 번째 실행 python-function-image-060-3을 Companion에서 접수했다. 두 번째 실행은 전달 단계에 진입하지 않았으므로 미게시 태그 060-2를 그대로 사용한다. 재빌드 성공과 실제 Function probe는 별도로 확인한다.

## 수정 후 실제 Function 검증

2026-11-08 세 번째 이미지 실행은 build-and-test와 publish-python-function-image 모두 SUCCEEDED였다. 기본 entrypoint를 시작하고 POST /call로 probe를 보내는 검사도 통과했다. OCIR의 060-2 digest는 `sha256:3363eb6a5b4a56cc42638eb65ceb3fa6bd630460b3881c141894718b16f93349`다. 기존 Python Function에 이 digest를 적용하고 ACTIVE 상태에서 실제 OCI invoke probe 성공을 확인했다.

실제 Function 응답은 python-v1, x86_64, Python 경로 /opt/cpython-3.12/bin/python3였다. /tmp 전체·여유 공간은 805,306,368 bytes(768MiB), 메모리 제한은 3,221,225,472 bytes(3GiB), probe 시 관측 메모리 사용량은 39,038,976 bytes였다. 이는 소스 빌드의 최대 메모리·디스크 사용량이 아니다. 호출 로그의 요청 처리 시간은 87.593초였으며 콜드 스타트와 핸들러 처리 시간을 따로 측정한 값은 아니다.

배포 자동화 레슨런: update_function은 응답 본문이 없을 수 있다. 반환 data에서 Function ID를 읽으려다 실패했지만 이미지 갱신 자체는 성공했다. 재갱신 전에 get_function으로 적용 digest를 확인하고, 스크립트도 갱신 후 리소스를 다시 읽도록 수정했다. 쓰기 후 로컬 오류를 곧바로 원격 작업 실패로 취급하지 않는다.

이 시점의 남은 검증은 Companion의 Python 소스 빌드 실행, 결과 저장 IAM, 실제 테스트 보고서, foundation·앱 wheel 크기와 SHA-256 대조다. 브라우저 확장 프로그램 화면이 Companion 조작을 차단하여 아직 실행하지 않았다. Function probe 성공을 소스 빌드·VM 배포·OKE 배포 완료로 표시하지 않는다.
