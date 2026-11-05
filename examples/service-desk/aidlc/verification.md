# 첫 예제 검증 기록

2026-11-05, macOS ARM64 / Python 3.14에서 실행했습니다. 합성 업무·로컬 SQLite·데모 인증·결정적 라우터를 대상으로 한 결과입니다.

| 검증 | 실행 | 결과 |
| --- | --- | --- |
| 재현 설치 | `PYTHON=python3.14 bash scripts/setup.sh <foundation-path>` | 성공. Foundation 고정 커밋 확인, lock 설치, 앱 editable 패키징 |
| 통합 시험 | `.venv/bin/python -m pytest -q` | 7 passed, 1 warning |
| 실제 HTTP | `.venv/bin/python scripts/run_demo.py` 실행 후 `scripts/smoke.py` | PASS: 출처, 승인 전 미접수, 재승인 중복 방지, 요청 추적 연결 |
| 정적 검사 | Ruff | 통과 |
| Companion 설치 | `f56ed41`, JDK 21, `scripts/build.sh` | BUILD SUCCESS |
| Companion 연결 | 기존 OCI 프로파일로 웹 로그인 | 리전·구획 목록 조회 성공 |

시험 내용: FR1 출처·근거 없음, FR2 초안만 생성, FR3 재승인과 8개 병렬 승인에서 단일 접수, FR4 다른 사용자 세션·제안 거부 및 조회 격리, FR5 기억 보존·삭제·다음 세션 사용, FR6 성공·오류·승인 추적과 요청 ID 연결, NFR1 인증·권한, NFR2 파일 DB 재시작, NFR3 추적에 토큰·입력 원문 미포함. 허용하지 않은 모델 도구명과 잘못된 타입도 거부했습니다. 같은 요청 ID를 반복해도 추적 레코드가 충돌하지 않는 것을 확인했습니다.

설치 검증 중 기본 Python 3.9 환경과 문서 디렉터리의 자동 패키지 탐색 문제를 발견해 수정했습니다. 설치 스크립트가 Python 3.12 이상과 기존 가상환경 버전을 검사하며, 패키징은 service_desk 코드만 포함합니다. 수정 후 설치 명령을 다시 실행해 성공했습니다.

경고 1건은 Starlette TestClient의 httpx 사용 중단 예정 경고입니다. 현재 시험은 통과했고 이 경고를 없애기 위한 새 의존성 전환은 하지 않았습니다.

## 아직 검증하지 않은 범위

- 실제 모델 서비스 호출·모델 품질 평가와 JWT 공급자 인증.
- 실제 OCI 앱 빌드·배포, 운영 DB·TLS·네트워크·복구.
- Companion의 예제 배포 실행과 모니터링 연결.
- 전체 AgentCore 대체 기능: 네트워크 Gateway, 위임 Identity, 일반 Policy 엔진, 운영 관측·평가, 격리 Code Interpreter와 Browser.

현재 로컬 결과는 운영 준비 완료나 전체 플랫폼 구현 완료를 의미하지 않습니다. 다음 배포에는 리전·구획·대상 VM과 모델 연결 정보가 필요합니다. 실제 비밀값은 문서나 저장소에 기록하지 않습니다.
