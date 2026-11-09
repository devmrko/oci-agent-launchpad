# 검증한 출장비 앱을 ZIP으로 전달하기

**저장소 전체 대신 작은 ZIP을 전달해 다른 사람이 로컬에서 웹과 CLI를 실행할 수 있게 합니다.** 현재 예제의 코드·화면·테스트·명세와 실행 안내, 파일 해시, 테스트 결과를 함께 담습니다. Python 3.12 이상은 실행할 컴퓨터에 필요합니다.

이 기능은 출장비 예제용입니다. 임의 프로젝트를 자동 패키징하거나 OCI에 배포하는 기능은 아닙니다.

## 만드는 사람

저장소 루트에서 새 테스트 근거를 만들고 패키지에 연결합니다. 추가 Python 패키지와 OCI 계정은 필요하지 않습니다.

```sh
mkdir -p .run
python3 -S scripts/spec_evidence.py run specs/travel-allowance --output .run/package-evidence.json
python3 -S scripts/package_travel_demo.py build --evidence .run/package-evidence.json --output .run/travel-demo.zip
python3 -S scripts/package_travel_demo.py verify .run/travel-demo.zip
```

정상 결과는 각각 `PASS`, `PACKAGED`, `HASHES_MATCH`입니다. 실패한 테스트, 실행 후 코드 변경, 다른 명세의 근거, 빠진 파일, 기존 출력 ZIP은 거부합니다. 재생성할 때는 새 파일 이름을 사용하세요. 코드가 바뀌었다면 테스트부터 다시 실행합니다.

패키지 파일 목록은 코드에 명시되어 있습니다. 새 파일이 명세에 연결되면 목록도 검토해 갱신해야 합니다. 작업 폴더 전체나 `.env`, OCI 인증 파일을 자동 수집하지 않습니다. ZIP은 로컬 `.run`에 생성되며 자동 업로드·전송하지 않습니다.

## 받는 사람

ZIP을 새 폴더에 풀고 그 폴더에서 실행합니다.

```sh
python3 examples/enterprise-ai-web/cli.py 14
python3 examples/enterprise-ai-web/server.py --offline
```

첫 명령은 14박의 한도 `1400000`을 포함한 JSON을 반환합니다. 두 번째 명령은 로컬 웹 서버를 시작합니다. `http://127.0.0.1:8768`에서 숙박 일수를 선택해 계산하세요. 종료는 Ctrl+C이며, 포트가 사용 중이면 `--port 8769`를 추가합니다.

압축 안의 `RUN.md`에도 동일한 안내가 있습니다. 앱의 테스트는 다음 명령으로 다시 실행할 수 있습니다.

```sh
python3 -S -m unittest discover -s examples/enterprise-ai-web -p 'test_*.py'
```

## 전달되는 근거와 한계

- `test-evidence.json`: 생성 시 코드와 일치한 연결 테스트의 실행 결과입니다.
- `PACKAGE.json`: 압축에 포함한 각 파일의 SHA-256입니다. verify는 목록·경로·해시만 검사하며 코드를 실행하지 않습니다.
- `specs/travel-allowance/`: 요구, 설계, 작업 기록, 구현·테스트 연결입니다. 추가 문서 링크는 전체 저장소에서 확인할 수 있습니다.

해시 검사는 포함 파일과 기록이 일치하는지 확인하는 기능이며 작성자의 신원이나 변조되지 않은 배포 경로를 인증하는 전자서명이 아닙니다. 기록 자체도 수정할 수 있습니다. 수신 환경에서의 실제 실행은 별도로 확인해야 합니다.

검증에서는 ZIP을 새 임시 폴더에 풀고, 원본 checkout을 작업 폴더로 사용하지 않은 상태에서 CLI 14박 결과와 포함된 HTTP·CLI 테스트를 실행합니다. 브라우저 시각 배치, 실제 OCI 연결·운영 배포는 이 검증에 포함하지 않습니다.
