# 예제를 수정하고 검증하기

이 저장소는 요구 명세를 바탕으로 앱을 개발하고 OCI의 배포·운영으로 연결하는 알파 예제입니다. 작은 기능이나 문서를 개선한 뒤 다른 사람이 재현할 수 있는 변경으로 제안해 주세요.

## 계정 없이 확인하는 기본 경로

Git과 Python 3.12 이상을 준비하고 저장소 루트에서 실행합니다. 아래 범위는 Python 표준 라이브러리만 사용하며 OCI 계정과 추가 패키지가 필요하지 않습니다.

```sh
python3 -S -m unittest discover -s examples/enterprise-ai-web -p 'test_*.py'
python3 -S -m unittest discover -s scripts -p 'test_*.py'
python3 -S scripts/check_spec_links.py specs/travel-allowance
mkdir -p .run
python3 -S scripts/sdd_demo.py --output .run/contribution-demo
```

테스트는 `OK`, 링크 검사는 `links_valid`, 전체 체험은 `DEMO_PASS`로 완료됩니다. 전체 체험을 다시 실행할 때는 새 출력 폴더 이름을 사용하세요. `.run`의 결과는 커밋하지 않습니다.

## 변경을 제안할 때

- 해결하려는 문제와 사용자가 보게 될 동작을 설명합니다.
- 업무 규칙을 바꾸면 관련 명세·합격 조건·테스트를 함께 검토합니다. 제공 형태(API·MCP·웹 등)는 프로젝트에 맞게 정하며 고정 분류를 요구하지 않습니다.
- 추가하거나 옮긴 구현·테스트 파일이 명세 검증에 필요하면 `traceability.json` 연결을 갱신합니다.
- 실행한 검증 명령과 결과, 아직 확인하지 않은 범위를 PR 설명에 적습니다. 형식적인 문서 변경에 새 테스트를 만들 필요는 없습니다.

[새 요구로 시작하기](specs/spec-starter/README.md) · [전체 체험](specs/sdd-walkthrough/README.md) · [테스트 근거 읽기](specs/test-evidence/README.md)

## 자동 검증 범위

[Offline SDD checks](https://github.com/devmrko/oci-agent-launchpad/actions/workflows/offline-sdd.yml)는 main 변경과 pull request에서 Ubuntu·macOS / Python 3.12로 위 명령을 실행하도록 구성했습니다. Actions 탭에서 해당 커밋의 각 작업 결과와 실패 단계를 확인할 수 있습니다. 수동 실행도 가능합니다.

이 검사는 SDD 도구와 출장비 웹·CLI 예제를 대상으로 합니다. 실제 OCI 호출, 다른 앱·인프라 전체, 화면의 시각적 품질, 운영 배포를 검증하지 않습니다. 합성 데모 검토 기록은 실제 고객 승인이 아닙니다. 테스트가 통과해도 요구가 충분히 검증되는지는 리뷰가 필요합니다.

워크플로에는 저장소 읽기 권한만 부여하며 OCI 비밀값을 전달하지 않습니다. 코드 가져오기와 Python 준비에는 GitHub 네트워크를 사용합니다. Actions의 설정은 [checkout](https://github.com/actions/checkout)과 [setup-python](https://github.com/actions/setup-python)의 공식 안내를 참고했습니다.
