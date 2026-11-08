# 에이전트를 실행할 비공개 OKE 만들기

VM에서 검증한 에이전트를 별도 Kubernetes 환경에서도 실행하려는 OCI 엔지니어를 위한 Terraform 구성이다. 전용 VCN·NAT·Service Gateway·비공개 서브넷·Enhanced cluster·관리형 노드 풀을 만든다. 기존 클러스터를 수정하지 않는다. 클러스터 생성과 에이전트 배포 성공은 별개다.

## 입력과 용량

모든 환경 입력은 `terraform.tfvars.example`을 복사한 별도 파일로 제공한다. 실제 노드 이미지 ID는 해당 리전의 OKE Node Pool Options에서 Kubernetes 버전과 AMD64 shape에 맞게 선택한다. 예제 ID를 그대로 적용하지 않는다. OCI 프로파일은 기본 `DEFAULT`다.

- `vcn_cidr`: 기존 VCN·연결 대상·온프레미스와 겹치지 않는 IPv4 /16. 내장 Pod `10.244.0.0/16`, Service `10.96.0.0/16`와도 구분한다.
- `node_capacity`: OS, 이미지, 업데이트 중 중복 이미지, 로그, 임시 작업, 여유를 각각 GiB로 명시한다. Terraform은 합계를 GB로 환산해 부트 볼륨과 비교한다. 실제 게스트 파일시스템의 여유는 노드 생성 후 다시 확인해야 한다.
- 첫 검증은 1노드·1앱 Pod다. 노드를 늘리는 것만으로 SQLite 앱이 다중 replica를 지원하지는 않는다. 업무 데이터 PVC는 부트 볼륨 예산과 별도다.

## 실행 순서

저장소 루트의 `.tools/terraform/terraform` 또는 설치된 동등 버전을 사용한다. 실행 계정에는 새 네트워크·OKE·Compute 리소스 생성 권한이 필요하며 유료 리소스가 생성된다.

```sh
terraform -chdir=infra/terraform/oke init
terraform -chdir=infra/terraform/oke validate
terraform -chdir=infra/terraform/oke test
terraform -chdir=infra/terraform/oke plan -var-file=/absolute/path/oke.tfvars.json -out=/absolute/path/oke.tfplan
terraform -chdir=infra/terraform/oke apply /absolute/path/oke.tfplan
```

State와 계획 파일은 접근을 제한하고 Git에 넣지 않는다. 실제 구성을 변경할 때 기존 state를 사용해야 한다. 새 state로 같은 이름의 리소스를 중복 생성하지 않는다.

## 생성 후 연결해야 할 부분

API와 노드는 공인 주소를 갖지 않는다. API에 접근할 비공개 운영 경로와 OCI DevOps private network channel을 준비해야 한다. OCI 서비스 접근은 Service Gateway, 외부 통신은 NAT를 사용한다. 출력 `nat_public_ip`는 실제 경로 확인 후 ADB ACL에 사용할 수 있으며 기존 ACL을 보존한다.

이 모듈은 다음 항목을 자동 구성하지 않는다: Langfuse VCN 피어링·보안 규칙, workload identity IAM, Vault Secret 동기화, OCIR pull 인증, DevOps OKE 배포 환경·파이프라인, PVC·앱 배포. [OKE 전체 설계](../../../deploy/OKE-DESIGN.md)와 [배포 명세](../../../deploy/OKE-MANIFESTS.md)를 따라 연결한다.

API 보안 목록은 전용 VCN에서 6443/12250만 수신한다. 노드는 같은 노드 서브넷, API의 kubelet 연결, VCN 내부 경로 MTU 검사만 수신한다. 외부에서 접근하는 앱 LoadBalancer와 인터넷 공개 SSH는 만들지 않는다. NAT를 통한 아웃바운드는 허용하므로 운영 환경의 세부 egress 통제는 별도 정책으로 추가한다.

## 검증 범위

2026-11-08 provider 8.29.0 스키마 검증과 mock 계획 테스트 4개 통과. 실제 서울 계획은 11개 생성, 변경·삭제 0개였으며 적용을 완료했다. OCI API에서 클러스터와 첫 노드 ACTIVE를 확인했다. 아직 Kubernetes 노드 Ready·모델·메모리·관측 연결 성공을 의미하지 않는다.

근거: [Oracle Cluster Terraform 리소스](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/containerengine_cluster.html), [Node Pool 리소스](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/containerengine_node_pool.html).

## 실제 파일시스템 용량과 비공개 운영 접근

2026-11-08 실제 노드는 Ready였지만 100GB 부트 볼륨의 루트 파일시스템은 29.4GiB에 그쳤다. 이미지도 같은 파일시스템을 사용했다. `oci-growfs -y`와 kubelet 재시작 후 용량 88,944,410,624 bytes(약 82.8GiB), 여유 76,555,526,144 bytes(약 71.3GiB)를 확인했다. 볼륨 크기와 게스트의 사용 가능 공간은 별도로 검사해야 한다.

`node-init.sh.tftpl`은 새 노드에서 루트를 확장하고 `node_capacity` 합계 이상의 실제 루트 용량을 확인한 뒤 OKE 기본 초기화를 실행한다. 이미지별 별도 파티션(/var/oled 등)이 공간을 차지하므로 볼륨 예산만 통과하고 실제 루트 예산이 부족할 수 있다. 이 경우 초기화가 실패하도록 차단한다. 운영 전에는 부트 볼륨을 더 크게 산정해야 한다. 기존 노드에 metadata를 갱신해도 cloud-init이 다시 실행되지는 않는다. 이번 기존 노드는 수동 확장을 검증했으며 새 노드 자동 초기화는 아직 실측하지 않았다.

`private_peer`는 선택 입력이다. 피어링 gateway, 목적지 /32 목록, 운영자 사설 /32를 받는다. 기존 NAT와 Service Gateway 경로를 보존하고 API 6443 접근만 추가한다. 이번에는 관측 서버를 통해 로컬에만 바인딩한 SSH 터널을 만들고, 원래 API 주소를 TLS server name으로 지정해 인증서 검증을 유지했다. API 공인 주소나 인터넷 입력 규칙은 만들지 않았다.

검증: Terraform 모의 provider 테스트 6개 통과, 실제 피어링 경유 Kubernetes API 접속 및 노드 Ready 확인. 진단·확장에 사용한 임시 관리자 Pod 두 개는 삭제했다. 이 결과는 앱·모델·메모리·Langfuse 연결 검증을 대신하지 않는다.

근거: [Oracle OKE 노드 루트 확장](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengextendingrootpartitionmanually.htm), [OKE 초기화 스크립트](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengusingcustomcloudinitscripts.htm).
