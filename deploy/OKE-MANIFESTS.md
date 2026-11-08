# 같은 에이전트를 OKE에 올릴 배포 명세 준비하기

OCI 엔지니어가 VM에서 검증한 service-desk를 OKE로 옮길 때 사용할 명세 생성기다. 환경별 namespace·이미지·모델·비밀 참조를 입력하면 적용 순서대로 JSON 명세 5개를 만든다. **현재 로컬 생성·검증 단계이며 실제 OKE 배포 성공을 의미하지 않는다.**

## 구성과 준비 조건

| 구성 | 역할 / 필요한 준비 |
|---|---|
| Enhanced OKE | workload identity 사용. 전용 namespace와 ServiceAccount에 OCI 권한 부여 |
| OCIR 이미지 | Functions에서 만든 검증된 wheel을 포장. 태그 대신 digest 입력 |
| Namespace / ServiceAccount | 앱의 실행 범위와 OCI 인증 주체 |
| PVC | SQLite 업무 데이터 저장. ADB의 에이전트 기억과 별도 |
| Deployment | 1 Pod, Recreate 교체. 합성 예제의 토큰 인증 사용 |
| ClusterIP Service | 클러스터 내부 8092 포트. 외부 공개 없음 |
| 런타임 Secret / pull Secret | 별도로 생성해야 함. 이 생성기는 비밀값을 받거나 생성하지 않음 |

[전체 설계](OKE-DESIGN.md)에 따라 전용 클러스터·네트워크·IAM·Vault 연결을 먼저 준비해야 한다. 노드 디스크에는 OS와 이미지, 로그, 임시 공간을 합산하고 PVC는 별도로 산정한다. 명세의 512Mi/2Gi 메모리 request/limit과 256Mi/1Gi 임시 저장소 request/limit은 첫 검증용이며 실측된 운영 권장값이 아니다. 여러 Pod와 HA는 지원하지 않는다.

## 생성하기

저장소 루트에서 아래와 같은 설정 파일을 준비한다. 모든 필드는 필수다. `image`는 실제 빌드·검증한 OCIR digest, `source_build_id`는 그 출처인 Functions 빌드 ID로 바꾼다. 생성기는 문자열을 검증하지만 클라우드의 실제 출처 일치까지 확인하지 않으므로 배포 전 별도 대조해야 한다.

```json
{
  "namespace": "launchpad-oke",
  "service_account": "service-desk",
  "image": "icn.ocir.io/YOUR_NAMESPACE/service-desk@sha256:YOUR_64_HEX_DIGEST",
  "source_build_id": "YOUR_FUNCTIONS_BUILD_ID",
  "model_region": "us-ashburn-1",
  "model_compartment": "YOUR_COMPARTMENT_OCID",
  "model_name": "YOUR_MODEL_ID",
  "runtime_secret": "desk-runtime",
  "image_pull_secret": "ocir-pull",
  "storage_class": "oci-bv",
  "pvc_gib": 50
}
```

```sh
python3 deploy/render_oke.py --config /path/to/oke-input.json --output /path/to/new-manifests
```

출력 폴더는 새 폴더여야 한다. Namespace → ServiceAccount → PVC → Deployment → Service 순서로 생성한다. JSON은 Kubernetes가 받는 형식이며 DevOps manifest artifact로 등록할 때 이 순서를 유지한다. 생성만으로 클라우드 리소스를 만들지는 않는다.

## 비밀 주입 계약

같은 namespace의 `runtime_secret`에 다음 키가 필요하다. 비밀은 Vault에서 제한된 권한으로 전달하는 별도 경로를 구성해야 한다. **Vault → Kubernetes Secret 동기화는 아직 이 생성기에 구현되지 않았다.** 평문 Secret 파일을 Git에 추가하거나 DevOps 로그에 출력하지 않는다.

| Secret 키 | 앱 전달 방식 |
|---|---|
| `memory.json` | `/run/desk-secrets/memory.json`, 읽기 전용 0440 파일 |
| `demo-accounts.json` | `DESK_DEMO_ACCOUNTS`, 기존 합성 예제 계정 형식 |
| `langfuse-url` | `DESK_LANGFUSE_URL`, 비공개 주소 |
| `langfuse-public-key` / `langfuse-secret-key` | 각각 Langfuse 환경변수 |
| `langfuse-capture-content` | 합성 입출력 검증에 한해 문자열 `true`, 그 외 `false` |

`memory.json`은 앱의 기존 메모리 설정 형식이며 DB 사용자·암호·DSN·임베딩 설정과 **VM과 구분한 namespace**를 포함한다. pull Secret은 같은 namespace에서 OCIR 접근에 사용한다.

Kubernetes의 Secret 파일은 심볼릭 링크다. 현재 Langfuse 파일 로더는 링크를 거부하므로 Langfuse는 개별 환경변수로 주입한다. Memory 파일 로더는 해당 파일 마운트를 사용할 수 있다. 둘 다 시작 시 읽으므로 비밀 교체 후 Pod 재생성과 모델·메모리·관측 검증이 필요하다. 런타임 Secret 전체를 `envFrom`으로 노출하지 않는다.

## 성공을 판단하는 방법

startup/readiness는 `/health`에서 로컬 SQLite 연결을 확인한다. liveness는 TCP 포트만 확인하므로 모델·ADB 장애를 직접 재시작 조건으로 삼지 않는다. TCP 검사는 업무 정상 동작을 증명하지 않는다. 시작 시 ADB 연결 실패는 앱 기동을 막을 수 있다.

실제 완료에는 이미지 기동, workload identity 권한, ADB ACL과 Langfuse 경로, 모델 응답, 세션 간 기억, Langfuse 관측·입출력 정책, Pod 재생성 후 PVC 데이터 보존 검사가 모두 필요하다. Companion의 OKE 대상 검증·실행 지원과 실제 배포는 후속 작업이다.

근거: [OKE workload identity](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm), [DevOps의 OKE manifest 순차 적용](https://docs.oracle.com/en-us/iaas/Content/devops/using/deploy_oke.htm).

## 컨테이너 이미지 빌드 경로

앱 소스 빌드는 OCI Functions가 맡고, 컨테이너 포장은 OCI DevOps Managed Build가 맡는다. `prepare_container.py`로 검증된 릴리스 ZIP을 풀어 `container/`를 준비한 뒤 [이미지 빌드 명세](container_build_spec.yml)를 `build_spec.yml`로 사용한다. 빌드 저장소에는 `container/`와 `deploy/probe_build_runner.py`만 필요하다. 런타임 계정·DB·Langfuse 비밀은 포함하지 않는다.

빌드 실행기는 Podman overlay, 여유 디스크 최소 16GiB, 메모리 제한 최소 4GiB를 확인한다. 디스크 예산은 기반 이미지/레이어 4GiB + 설치/중간 결과 4GiB + 전달용 이미지 4GiB + 여유 4GiB다. 명세는 오프라인 wheel 설치와 `pip check`, 주요 import, 기본 실행 명령으로 시작한 비root·읽기 전용 컨테이너의 `/health`와 버전을 검사한다. `/data`와 `/tmp`는 이 검사에서만 임시 파일시스템을 사용한다. 실제 OKE에서는 `/data`를 PVC로 바꾼다.

이 검사는 합성 모드의 기동 검사다. OCI 모델·ADB·Langfuse와의 실제 연결 및 PVC 보존은 증명하지 않는다. `service-desk-image` 출력은 별도 전달 단계에서 전용 비공개 OCIR 저장소로 게시하고, 최종 성공 후 registry digest를 조회해 배포 명세에 넣는다. 빌드 단계 성공만으로 게시 완료로 판단하지 않는다.

2026-11-08 Companion에서 `launchpad-service-desk-image` 파이프라인을 실행했다. 소스는 전용 `oke-service-desk-060` 브랜치, 포장 대상은 Functions 빌드 `b874b66b-9c95-43b5-a0c1-8c07a32d8afe`의 0.6.0이다. 실행 중인 Companion에는 OKE 검증 기능을 반영했고 브라우저에서 기존 VM 대상 확인도 재검증했다. 이 문서 작성 시 이미지 빌드는 실행기 할당 중이며 OKE 미배포다.

### 실제 빌드에서 확인한 Podman 제약

첫 실행은 이미지 생성·`pip check`·주요 import까지 성공했으나, 기동 검사 명령의 `--tmpfs /data:uid=10001,gid=10001,mode=0700`를 OCI 실행기가 `unknown mount option`으로 거부했다(종료 코드 125). 이미지 생성 성공을 배포 가능 판정으로 간주하지 않고 전달 단계를 차단했다.

검사 전용 `/data`·`/tmp`를 `rw,mode=1777`인 독립 tmpfs로 변경했다. 앱은 여전히 UID 10001, 읽기 전용 루트, capability 제거 상태로 실행한다. 임시 디렉터리는 해당 검사 컨테이너 수명에 한정되며 실제 OKE의 PVC·fsGroup 설정을 대체하지 않는다. 수정본 `136bc59`를 Companion에서 `service-desk-060-oke-image-2`로 재실행했다. 재실행의 기동 검사와 OCIR 게시 결과는 아직 확인 중이다.

두 번째 실행은 tmpfs 옵션을 통과했으나 합성 모드의 필수 `DESK_DEMO_ACCOUNTS` 누락으로 앱 시작에 실패했다. 로그의 종료 코드 137만 보고 메모리 부족으로 단정하지 않고 실제 `ValueError`를 확인했다. 검사 실행 시 무작위 임시 토큰과 합성 subject를 생성해 주입하고, demo 인증·모델 모드를 명시했다. 같은 환경 입력과 빌드에 사용한 foundation 소스로 로컬 `/health`의 UP·0.6.0을 확인했다. 로컬 검증은 Linux 컨테이너 검증을 대체하지 않는다. 수정 소스 `5397c2e`의 세 번째 빌드를 Companion에서 시작했으며 결과는 아직 확인 중이다.
