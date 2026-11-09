# 기존 저장소에 명세와 검증 연결하기

**Launchpad로 프로젝트를 옮기지 않고 기존 코드·테스트에 요구 명세를 연결합니다.** 이 절차는 공개 OCI Companion의 작은 HTTP 예제를 별도 폴더에 받아, 변경 요청 → 실패 테스트 → 구현 → 검토 보고서까지 진행합니다. OCI 계정·AI 도구·추가 Python 패키지는 필요하지 않습니다.

예제의 변경 요청은 “`/`와 `/healthz`는 정상 상태를 반환하고 없는 경로는 404로 응답한다”입니다. 원래 코드는 모든 경로에 200을 반환합니다. 여기서는 HTTP 앱을 선택했으며 Launchpad 사용에 특정 앱 형태를 요구하지 않습니다.

## 준비와 기존 테스트 연결

Git, Python 3.12 이상과 내려받은 Launchpad가 필요합니다. macOS·Linux의 bash/zsh에서 **Launchpad 저장소 루트**를 현재 폴더로 두고 실행하세요. 외부 앱은 임시 폴더에 복제하며 모든 수정은 이 복사본에만 적용합니다. 기존 개인 작업 폴더나 원격 Companion 저장소는 수정하지 않습니다.

```sh
launchpad_root="$PWD"
companion_root="$(mktemp -d /tmp/launchpad-companion.XXXXXX)"
git clone https://github.com/devmrko/oci-companion.git "$companion_root"
git -C "$companion_root" checkout --detach cca3de046aaca448aad18915a6a7019ab7ec0531
mkdir -p "$companion_root/specs/container-health" .run
cp specs/external-project/companion/spec.md specs/external-project/companion/design.md specs/external-project/companion/tasks.md specs/external-project/companion/traceability.json "$companion_root/specs/container-health/"
cp specs/external-project/companion/test_sdd.py "$companion_root/examples/container-demo/"
python3 -S scripts/spec_evidence.py run specs/container-health \
  --root "$companion_root" --output .run/companion-before.json
```

`PASS`와 테스트 3개가 나옵니다. 기존 pytest 함수 두 개를 `test_sdd.py`의 unittest가 호출하고, 추가 테스트가 실제 루프백 HTTP 요청으로 `/`를 검사합니다. `test_app.py`도 연결 파일에 포함해 변경 시 해시 검사 대상이 되도록 했습니다.

이 연결 방식은 fixture가 없는 단순 함수에 한정됩니다. pytest fixture·플러그인·매개변수화나 다른 언어의 테스트를 자동 지원하지 않습니다. 테스트 프레임워크를 바꿀 필요 없이 연결할 수 있는 범위를 실제 코드에서 먼저 확인해야 합니다.

## 변경 요청을 남기고 실패 확인

```sh
python3 -S scripts/developer_handoff.py prepare specs/container-health \
  --root "$companion_root" --requirement REQ-002 \
  --request 'GET /healthz는 200, 미등록 경로는 JSON 404로 응답하고 기존 루트와 상태 응답은 유지한다.' \
  --acceptance 'GET /와 /healthz는 200이고 /missing은 404이다. 기존 테스트를 유지한다.' \
  --output .run/companion-task
git -C "$companion_root" apply --check "$launchpad_root/specs/external-project/companion/acceptance.patch"
git -C "$companion_root" apply "$launchpad_root/specs/external-project/companion/acceptance.patch"
python3 -S scripts/spec_evidence.py run specs/container-health \
  --root "$companion_root" --output .run/companion-red.json
```

마지막 명령은 의도적으로 **종료 코드 2, `NOT_PASSED`**가 됩니다. `/missing`에 404를 기대하는 새 테스트가 기존 200 응답 때문에 실패합니다. 여기서 멈추고 결과를 확인한 뒤 다음 단계로 진행하세요. 패치는 새 명세·테스트·연결만 추가합니다.

## 구현하고 검토 보고서 만들기

```sh
git -C "$companion_root" apply --check "$launchpad_root/specs/external-project/companion/implementation.patch"
git -C "$companion_root" apply "$launchpad_root/specs/external-project/companion/implementation.patch"
python3 -S scripts/spec_evidence.py run specs/container-health \
  --root "$companion_root" --output .run/companion-green.json
python3 -S scripts/spec_evidence.py check .run/companion-green.json --root "$companion_root"
python3 -S scripts/developer_handoff.py report .run/companion-task/baseline.json \
  --root "$companion_root" --evidence .run/companion-green.json \
  --output .run/companion-review
git -C "$companion_root" diff -- examples/container-demo/app.py
```

테스트 5개가 `PASS`, 파일 확인은 `CURRENT`, 보고서는 `TESTS_CURRENT_REVIEW_PENDING`이 됩니다. `REVIEW.md`에서 요청·변경 파일·기존 테스트 유지 여부를 확인합니다. 코드가 바뀌었으므로 기준 비교의 `REVIEW_REQUIRED`는 정상입니다. 사람이 요구 충족 여부를 검토해야 하며 자동 승인·원격 반영·배포는 하지 않습니다.

패치의 경로 판별은 쿼리 문자열을 포함한 정확한 일치입니다. `/healthz?probe=1`은 404이며 범용 HTTP 라우터를 구현한 것은 아닙니다. 실무에서는 필요한 URL 규칙을 명세와 테스트에 추가하세요.

## 자신의 프로젝트로 바꾸기

- `--root`에는 실제 프로젝트 루트, 명세 인자에는 그 루트 기준 명세 폴더를 지정합니다.
- `spec.md`에는 요구 ID와 합격 조건, `design.md`에는 구현 방향, `tasks.md`에는 작업을 기록합니다.
- `traceability.json`에는 실제 구현·테스트 경로와 unittest 클래스·메서드를 연결합니다. 가져오는 로컬 의존 파일도 해시 대상에 포함하세요.
- 새 기능은 기존 테스트 통과만으로 판단하지 말고 새 합격 조건의 실패·성공을 확인합니다.

결과 파일은 현재 터미널 폴더 기준이고 덮어쓰지 않습니다. 재실행할 때는 새 복제 폴더와 `.run/companion-*-2` 같은 새 출력 이름을 사용하세요. 명세·연결 파일은 직접 편집할 수 있고 특정 IDE·모델·API를 강제하지 않습니다.

## 확인한 범위

2026-11-10, 위 공개 커밋의 새 복사본에서 macOS / Python 3.15.0으로 기준 3개 통과 → 새 조건 실패 → 구현 후 5개 통과 → 현재 근거가 있는 검토 보고서 생성을 확인했습니다. 개발 작업은 이 세션에서 수행했으며 독립 사용자의 인수 테스트가 아닙니다. Companion 전체 테스트·빌드·OCI·컨테이너 배포는 실행하지 않았습니다. 원격 저장소에 기능 변경을 반영하지 않았습니다.

자료의 `tasks.md`는 실행 전 체크리스트입니다. 실제 실행 결과는 사용자가 생성한 JSON·보고서를 확인하고 체크하세요. 테스트 코드는 로컬 권한으로 실행되며 별도의 보안 샌드박스가 아닙니다.
