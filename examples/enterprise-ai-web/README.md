# 출장비 규정 계산과 OCI Enterprise AI 체험

숙박 일수를 선택하면 가상 규정으로 한도를 계산합니다. OCI 모드에서는 AI 설명과 Python 실행 코드·출력을 추가로 확인할 수 있습니다. 회사 자료를 사용하지 않는 학습용 앱입니다. [요구·설계·테스트가 연결된 SDD 명세](../../specs/travel-allowance/README.md)를 함께 제공합니다.

## 계정 없이 먼저 실행하기

Python 3.12 이상에서 저장소 최상위로 이동해 실행합니다. 패키지 설치와 OCI 인증이 필요하지 않습니다.

```sh
python3 examples/enterprise-ai-web/server.py --offline
```

`http://127.0.0.1:8768`에서 **규정으로 계산하기**를 누르면 2박은 20만 원으로 표시됩니다. 이는 서버의 정해진 규정 계산이며 AI 호출이 아닙니다. 이 모드에서는 실제 OCI 요청 경로를 거부합니다. 아래는 선택적인 실제 AI 연결 절차입니다.

## 실행 범위

웹 서버는 이 컴퓨터의 `127.0.0.1`에서만 실행합니다. 실제 모델과 계산 도구는 지정한 OCI 리전에 요청하므로 호출 비용이 발생할 수 있습니다. 로그인 키는 서버의 `~/.oci/config` DEFAULT 프로필에서 읽으며 브라우저에 전달하지 않습니다.

입력은 숙박 1~10박과 계산 도구 사용 여부로 제한합니다. 한 번에 한 요청, 서버 실행당 최대 10회로 제한하며 실패한 요청도 횟수에 포함합니다. 서버를 재시작하면 횟수는 초기화됩니다. 모델 오류를 가짜 응답으로 바꾸지 않습니다. 임시 계산 컨테이너는 응답 후 삭제를 시도하며 실패하면 화면에 표시합니다.

## 시작하기

macOS 또는 Linux에서 Python 3.12 이상을 사용합니다. Windows에서는 WSL 환경을 사용하세요. 아래 설치 절차는 macOS에서 검증했으며 Linux·WSL은 아직 검증하지 않았습니다.

준비할 것은 다음 세 가지입니다.

1. OCI 사용자 서명 인증: `~/.oci/config`의 DEFAULT 프로필과 해당 키 파일. 키를 이 저장소에 복사하지 않습니다.
2. 사용할 리전의 Generative AI 프로젝트: 콘솔의 **Analytics & AI → Generative AI → Projects**에서 생성하고 `ACTIVE`가 된 뒤 OCID를 복사합니다.
3. 해당 구획의 모델·프로젝트 사용 권한. 이 앱은 IAM 정책이나 OCI 프로젝트를 자동으로 생성하지 않습니다. [Oracle 프로젝트·인증 준비 안내](https://docs.oracle.com/en-us/iaas/Content/generative-ai/get-started-agents.htm)를 참고하세요.

이 예제는 Python Foundation이나 Companion 저장소 권한 없이 실행할 수 있습니다. 처음 받는 경우 아래처럼 복제하고, 이미 받았다면 저장소 최상위로 이동합니다.

```sh
git clone https://github.com/devmrko/oci-agent-launchpad.git
cd oci-agent-launchpad
bash examples/enterprise-ai-web/setup.sh

# 이 점검은 로컬 패키지·인증 파일만 확인하며 OCI 호출 비용은 발생하지 않습니다.
.run/enterprise-ai-venv/bin/python examples/enterprise-ai-web/server.py --check

# 아래 프로젝트 OCID는 본인의 ACTIVE 프로젝트 값으로 바꿉니다.
.run/enterprise-ai-venv/bin/python examples/enterprise-ai-web/server.py \
  --region us-ashburn-1 --project '<프로젝트 OCID>'
```

기본 `python3`가 3.12 미만이면 `PYTHON=python3.12 bash examples/enterprise-ai-web/setup.sh`처럼 실행 파일을 지정합니다. `--check` 통과는 OCI 서버에서의 인증·권한 검증을 뜻하지 않습니다.

브라우저에서 `http://127.0.0.1:8768`을 엽니다. 종료는 실행한 터미널에서 Ctrl+C를 누릅니다. 포트가 사용 중이면 `--port`로 바꿀 수 있습니다.

사용한 직접 의존성 버전을 `requirements.txt`에 고정했습니다. 하위 의존성 전체나 다른 운영체제까지 고정·검증한 lock 파일은 아닙니다.

## 확인할 결과

2박을 선택하면 한도는 20만 원입니다. 계산 도구를 선택하면 완료된 도구의 출력이 정확히 `200000`인지 검사합니다. 틀린 금액·실행 출력 누락·빈 최종 답변은 각각 다른 상태로 표시합니다. 도구를 끈 경우에는 모델 답변 수신만 표시하며 정답 검증을 주장하지 않습니다. 최종 답변의 문장 내용과 컨테이너 정리 상태도 직접 확인하세요. 이 앱은 파일 검색·대화 기억·앱의 OCI 호스팅을 시험하지 않습니다.

경계 검증은 `python3 -m unittest discover -s examples/enterprise-ai-web -p 'test_*.py'`로 실행합니다. 실제 OCI 호출은 화면에서 별도로 확인합니다.

2026년 11월 9일 경계·결과 판정 테스트 8건이 통과했습니다. 로컬 HTTP 경로의 실제 OCI 호출에서 3박 입력의 `print(100000 * 3)` 실행 출력 `300000`, 최종 답변 30만 원, 임시 계산 환경 삭제를 확인했습니다. 브라우저 자동화 연결 장애로 화면 클릭과 시각적 배치는 검증하지 못했습니다.

같은 Mac의 별도 빈 가상환경에서도 설치 스크립트, 의존성 검사, `--check`, 테스트 8건과 실제 1박 질문 응답을 확인했습니다. 기존 OCI 계정 설정은 사용했으므로 새 계정·테넌시 준비까지 재현한 결과는 아닙니다. 기본 출력 한도에서 답변 절단이 관측되어 한 문장 응답을 요청하고 출력 한도를 1,024토큰으로 조정했습니다. 미완료 응답은 계속 실패 상태로 표시합니다.

## 실행이 안 될 때

| 증상 | 확인할 것 |
|---|---|
| 패키지를 찾지 못함 | 설치와 실행 모두 같은 `.run/enterprise-ai-venv/bin/python` 환경인지 확인합니다 |
| OCI 호출 실패 | 로컬 OCI 인증과 대상 구획 권한, 프로젝트 ACTIVE 상태, 모델의 리전 지원을 확인합니다. 서버에는 오류 종류만 출력됩니다 |
| 로컬 주소로 접속하라는 메시지 | `localhost` 대신 안내된 `http://127.0.0.1:8768` 주소로 접속합니다 |
| 체험 한도 도달 | 실행당 최대 10회입니다. 더 시험하려면 서버를 종료하고 다시 실행합니다. 실패한 호출도 횟수에 포함됩니다 |
| 계산 도구 출력 불일치 | 코드와 원문 출력을 확인합니다. 실행 성공과 계산 정확성을 구분하므로 불일치는 성공으로 처리하지 않습니다 |
| 임시 환경 삭제 실패 | 서버에 표시된 컨테이너 ID를 사용해 OCI에서 정리합니다. 호출 자체가 중단돼 응답을 못 받은 경우에도 자원 상태를 확인합니다 |

더 보기: [Enterprise AI 설명과 첫 체험](../../docs/oci-enterprise-ai-introduction.md).
