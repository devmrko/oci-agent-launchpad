# 업무 앱에서 사설 Langfuse로 연결하기

다른 VCN의 업무 VM이 SSH 터널 없이 Langfuse private Load Balancer에 실행 기록을 보내도록 연결합니다. Companion은 이 통신 경로에 참여하지 않습니다. 같은 리전의 기존 VCN 두 개를 대상으로 합니다.

## 소유 범위와 입력

이 모듈은 LPG 두 개와 기존 관측 VCN의 경로표를 관리합니다. `region`, `compartment_id`, 두 VCN ID, `app_client_cidr`, `lb_cidr`, 기존 경로표 이름·태그·경로 목록이 필수입니다. 클라이언트와 LB 주소는 해당 환경의 사설 /32를 사용합니다. 기존 경로표의 전체 경로·태그를 먼저 조회해 보존해야 하며 다른 Terraform 상태가 소유한 경로표를 중복 import하면 안 됩니다.

1. 기존 관측 경로표를 조회하고 `existing_routes`, `existing_route_*` 변수에 그대로 반영합니다. 현재 모듈은 destination·destination_type·network_entity_id만 보존하는 단순 정적 경로표용입니다. 설명·특수 경로 속성이 있는 환경은 먼저 모델을 확장해야 합니다.
2. `terraform init` 후 기존 경로표 ID를 `oci_core_route_table.observability`로 import합니다. 이 모듈에서 경로표를 새로 생성해도 기존 서브넷에는 자동 연결되지 않습니다.
3. plan에서 기존 경로 보존, LPG 두 개 생성과 앱 주소 반환 경로만 추가되는지 확인하고 apply합니다.
4. `app_route` 출력을 업무 VCN을 소유한 상위 모듈의 `private_peer_routes`에 추가하고 그 상태에서 apply합니다.
5. 관측 모듈의 `ingestion_client_cidrs`에 앱 /32를 추가합니다. 이 규칙은 private LB TCP 8080만 허용합니다. 실제 허용 범위는 함께 적용된 Security List/NSG 규칙 전체로 판단해야 합니다.
6. 앱 VM에서 private LB `/api/public/health`와 인증된 관측 전송을 확인합니다.

## 확인된 결과와 한계

2026-11-07 서울: LPG 상태 PEERED, 앱→LB /32 및 관측 VCN→앱 /32 경로, LB 입력 NSG 규칙을 적용했습니다. 기존 두 인터넷 경로는 유지했고 삭제한 자원은 없습니다. 앱 VM의 직접 HTTP health는 OK·Langfuse 4.76.0이었습니다.

앱 전용 계정으로 0.5.0 소스를 격리 실행하고 `/etc/launchpad/langfuse.json`(root 소유·앱 그룹 읽기, 0640)을 읽어 부모·모델 미사용 분기·도구 기록 3개를 전송했습니다. trace `fcfdac5ced485ee8144e311a28be9bcb`가 실제 Langfuse에 수신됐고 기본값에 따라 본문은 수집하지 않았습니다. SSH는 관리 명령 실행에만 사용했고 관측 전송 터널은 사용하지 않았습니다.

서비스 재배포·운영 TLS·다중 VM 고가용성·Vault 비밀 회전 자동화는 이번 검증 범위가 아닙니다. 신규 릴리스가 이 설정 파일을 참조하도록 활성화하는 단계가 남았습니다. 경로표는 삭제 방지 설정이 있으므로 폐기 시에는 기존 경로와 상태 소유권을 먼저 정리해야 합니다.

근거: [OCI Local VCN Peering](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/localVCNpeering.htm), [앱 관측 설정](../../../deploy/SERVICE-DESK-LANGFUSE.md).

## OKE 클라이언트 추가

선택 입력 `oke_peer`에 OKE VCN ID, 노드 서브넷 CIDR, API 서브넷 CIDR을 제공하면 전용 LPG 한 쌍과 관측 VCN의 반환 경로를 추가한다. 기존 VM 피어링과 인터넷 경로는 보존한다. 출력 `oke_gateway_id`를 OKE 모듈의 `private_peer`에 전달한다. OKE 쪽은 LB와 운영 서버 /32만 목적지로 사용하고 API는 운영 서버 /32의 6443만 허용한다.

2026-11-08 실제 적용: LPG 2개 생성, 기존 경로표 1개 갱신, 삭제 없음. 관측 서버에서 OKE API TCP 연결과 SSH 터널을 통한 Kubernetes 노드 Ready 조회를 확인했다. OKE→Langfuse LB의 입력 보안 규칙과 실제 관측 수신 검증은 아직 남았다. 피어링 연결만으로 애플리케이션 통신 성공을 주장하지 않는다.
