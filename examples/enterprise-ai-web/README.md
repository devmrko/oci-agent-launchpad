# OCI Enterprise AI 로컬 체험

숙박 일수를 선택하면 OCI 모델이 가상 출장 규정에 따라 한도를 계산합니다. 계산 도구를 선택하면 Python 실행 코드와 출력도 함께 확인할 수 있습니다. 회사 자료를 사용하지 않는 학습용 앱입니다.

## 실행 범위

웹 서버는 이 컴퓨터의 `127.0.0.1`에서만 실행합니다. 실제 모델과 계산 도구는 지정한 OCI 리전에 요청하므로 호출 비용이 발생할 수 있습니다. 로그인 키는 서버의 `~/.oci/config` DEFAULT 프로필에서 읽으며 브라우저에 전달하지 않습니다.

입력은 숙박 1~10박과 계산 도구 사용 여부로 제한합니다. 한 번에 한 요청, 서버 실행당 최대 10회로 제한하며 실패한 요청도 횟수에 포함합니다. 서버를 재시작하면 횟수는 초기화됩니다. 모델 오류를 가짜 응답으로 바꾸지 않습니다. 임시 계산 컨테이너는 응답 후 삭제를 시도하며 실패하면 화면에 표시합니다.

## 시작하기

저장소 최상위에서 실행합니다. OCI에 사용 가능한 ACTIVE 상태의 Generative AI 프로젝트와 모델 호출 권한이 필요합니다.

```sh
python3 -m venv .run/enterprise-ai-venv
.run/enterprise-ai-venv/bin/pip install openai oci-genai-auth
.run/enterprise-ai-venv/bin/python examples/enterprise-ai-web/server.py \
  --region us-ashburn-1 --project '<프로젝트 OCID>'
```

브라우저에서 `http://127.0.0.1:8768`을 엽니다. 종료는 실행한 터미널에서 Ctrl+C를 누릅니다. 포트가 사용 중이면 `--port`로 바꿀 수 있습니다.

## 확인할 결과

2박을 선택하면 한도는 20만 원입니다. 계산 도구를 선택한 경우에는 정답만 보지 말고 실행 코드, 출력 `200000`, 최종 답변, 컨테이너 정리 상태를 확인합니다. 이 앱은 파일 검색·대화 기억·앱의 OCI 호스팅을 시험하지 않습니다.

경계 검증은 `python3 -m unittest discover -s examples/enterprise-ai-web -p 'test_*.py'`로 실행합니다. 실제 OCI 호출은 화면에서 별도로 확인합니다.

2026년 11월 9일 경계 테스트 4건과 로컬 HTTP 경로의 실제 OCI 호출을 확인했습니다. 3박 입력에서 `print(100000 * 3)` 실행 출력 `300000`, 최종 답변 30만 원, 임시 계산 환경 삭제를 확인했습니다. 브라우저 자동화 연결 장애로 화면 클릭과 시각적 배치는 검증하지 못했습니다.

더 보기: [Enterprise AI 설명과 첫 체험](../../docs/oci-enterprise-ai-introduction.md).
