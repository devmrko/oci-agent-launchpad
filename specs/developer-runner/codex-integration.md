# Codex CLI 실행부터 원본 반영까지

실제 개발 도구가 작업 지시서를 받아 복사본을 수정하고, 독립적인 검증과 원본 충돌 확인을 거쳐 반영되는 흐름을 확인하는 사례입니다. Codex는 선택적 어댑터이며 프로젝트의 필수 도구가 아닙니다.

이번 합성 요구는 Hello Agent에서 `list cities`, `supported cities`를 대소문자·양끝 공백과 무관하게 지원하는 것입니다. 기존 한국어 도시 목록·시간·인사·허용 도구 검증을 유지하고, 부분 문자열이나 임의 명령을 새 도구로 취급하지 않습니다.

구현 전에 기존 REQ-004를 기준으로 작업 지시서를 생성합니다. 설치된 Codex CLI를 workspace-write·ephemeral 모드로 실행하고, 반환 diff와 새 테스트를 별도로 검토합니다. 원본의 기준 파일이 작업 전달 당시와 같을 때만 검토한 파일을 반영하고 다시 테스트합니다. 실제 고객 승인·OCI 호출·배포는 범위 밖입니다.

## 직접 실행하기

Python 3.12 이상과 설치·로그인한 Codex CLI가 필요합니다. CLI의 모델 이용 권한과 사용량 정책이 적용됩니다. Launchpad는 인증 정보를 복사하거나 CLI를 설치하지 않습니다. 저장소 루트에서 실행합니다.

```sh
python3 -S scripts/developer_handoff.py prepare specs/hello-agent \
  --requirement REQ-004 \
  --request '도시 목록 영문 표현의 경계 동작을 검토하고 필요한 테스트를 추가하세요.' \
  --acceptance '정확한 영문 표현은 목록을 반환하고 부분 문자열은 unsupported로 유지한다.' \
  --output .run/hello-codex-task
python3 -S scripts/developer_runner.py .run/hello-codex-task \
  --output .run/hello-codex-run --timeout 600 \
  -- python3 /absolute/path/to/oci-agent-launchpad/scripts/adapters/codex_exec.py '{task}'
python3 -S scripts/spec_evidence.py run specs/hello-agent \
  --root .run/hello-codex-run/workspace --output .run/hello-codex-evidence.json
python3 -S scripts/developer_handoff.py report .run/hello-codex-task/baseline.json \
  --root .run/hello-codex-run/workspace \
  --evidence .run/hello-codex-evidence.json --output .run/hello-codex-review
python3 -S scripts/developer_handoff.py check .run/hello-codex-task/baseline.json
```

어댑터 경로는 실제 저장소 절대 경로로 바꾸세요. 영문 표현 지원은 이미 반영되어 있으므로 위 예시는 경계 동작을 재검토하는 요청입니다. 각 실행에는 새 출력 경로를 사용합니다.

`CODEX_RESULT.md`는 도구의 최종 설명이고 `ADAPTER_RESULT.json`은 종료 상태입니다. 종료 코드가 0이어도 설명이 없거나 공백뿐이면 `EMPTY_RESPONSE`로 실패 처리합니다. 이전 결과 파일이 있는 작업 공간은 거부합니다. 설명이 있더라도 실제 구현 완료를 뜻하지 않습니다. diff·테스트·요구 충족 여부를 검토해야 합니다.

실행은 `codex exec --sandbox workspace-write --ephemeral`을 사용합니다. 호스트의 승인 정책을 유지하며 승인·샌드박스 우회 옵션을 사용하지 않습니다. 작업 폴더 분리의 한계는 [실행기 안내](README.md#실행-경계와-검증한-범위)를 참고하세요. [Codex 공식 비대화형 실행 안내](https://learn.chatgpt.com/docs/non-interactive-mode)도 함께 확인할 수 있습니다.

## 검토 후 반영

보고서가 `TESTS_CURRENT_REVIEW_PENDING`이고 기준 확인이 `UNCHANGED`인지 확인합니다. 이는 자동 승인이 아닙니다. 원래 요구·새 테스트·전체 diff를 읽고, 반영할 파일만 담은 패치를 별도로 준비합니다. 도구의 설명·임시 파일을 전체 복사하지 않습니다.

```sh
git apply --check /path/to/reviewed.patch
git apply /path/to/reviewed.patch
python3 -S -m unittest discover -s examples/hello-agent -p test_agent.py
python3 -S scripts/spec_evidence.py run specs/hello-agent \
  --output .run/hello-applied-evidence.json
```

기준 파일이 바뀌었다면 자동 덮어쓰기 대신 새 기준에서 충돌을 검토해야 합니다. 현재 제품에는 일반적인 자동 병합·승인 기능이 없습니다.

## 2026-11-10 실제 확인 결과와 한계

- 설치된 Codex CLI 0.167.0으로 기존 REQ-004의 영문 표현 두 개를 추가하도록 요청했습니다.
- 첫 실행은 호스트 권한으로 CLI 초기화에 실패했습니다. 승인된 재시도는 종료 코드 0이었지만 소스 변경과 최종 설명이 없었습니다. 이를 구현 성공으로 취급하지 않았습니다.
- 준비된 복사 작업 폴더에서 어댑터를 직접 재실행해 코드·테스트·명세 등 6개 파일의 변경을 받았습니다. 이 직접 재실행 결과는 앞선 실행기의 `run.json`에 자동 갱신되지 않으므로 별도의 기준 비교와 diff 검토를 수행했습니다.
- 도구가 보고한 테스트 결과와 별도로 Launchpad 검증기로 10개 테스트 통과, 기존 테스트 유지, 변경 기준 파일 일치를 확인했습니다. 검토한 6개 파일을 원본에 반영하고 테스트를 다시 실행했습니다.
- 빈 최종 설명을 성공으로 넘기지 않도록 어댑터를 보완했습니다. 이 보완은 모의 CLI 응답으로 검증했으며 실제 모델을 다시 호출한 결과로 보고하지 않습니다.

이 사례는 실제 개발 도구에서 변경을 받아 검토·반영한 작은 Python 예제입니다. 고객 승인, 실제 OCI 호출, 웹 통합, 배포, 다양한 프로젝트의 자동 병합 품질을 검증한 것은 아닙니다. CI는 어댑터의 명령 구성과 실패 처리를 모의 실행으로 검사하며 실제 Codex 로그인이나 모델 호출을 요구하지 않습니다.
