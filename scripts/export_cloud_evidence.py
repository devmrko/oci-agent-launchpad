"""Join an existing Hello Agent Job result to OCI and Langfuse read-only snapshots."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from package_travel_demo import sha
from requirement_handoff import read, write_new
from correlate_hello_release import attach

NAMES = {'hello-agent.chat': 'AGENT', 'oci.model': 'GENERATION', 'get_time': 'TOOL'}
CHECKS = {'health', 'authentication', 'model_and_tool', 'telemetry_export', 'langfuse_input_output'}


def require(condition):
    if not condition:
        raise ValueError('Evidence identities or required checks do not match')


def ocid(value, kind, region):
    require(isinstance(value, str) and re.fullmatch(
        r'ocid1\.' + kind + r'\.oc1\.' + re.escape(region) + r'\.[a-z0-9]+', value) is not None)
    return value


def entry(record, deployment, trace, scope, base, *, identity=None, evidence=None, root=None):
    require(set(scope) == {'profile','tenancy','user','demo','region','compartment'} and scope['demo'] is False)
    require(all(isinstance(scope[k], str) and scope[k] for k in scope if k != 'demo'))
    require(record['status'] == 'PASS' and record['execution_location'] == 'OKE')
    require(all(record['checks'].get(k) is True for k in CHECKS))
    require(record['chat_http_status'] == 200 and record['langfuse_http_status'] == 200)
    require(record['health']['agent_id'] == 'hello-agent' and record['health']['status'] == 'UP')
    version = record['health']['version']
    require(isinstance(version, str) and bool(version) and record['chat']['version'] == version)
    require(record['chat']['mode'] == 'oci' and record['chat']['telemetry'] == 'exported')
    delivery = record['delivery']
    require(delivery['job_completed'] is True and delivery['oci_deployment_state'] == 'SUCCEEDED')
    require(bool(delivery['job_name']) and bool(delivery['job_uid']))
    run = ocid(delivery['deployment_id'], 'devopsdeployment', scope['region'])
    d = deployment['data']
    require(d['id'] == run and d['compartment-id'] == scope['compartment'])
    require(d['lifecycle-state'] == 'SUCCEEDED')
    pipeline = ocid(d['deploy-pipeline-id'], 'devopsdeploypipeline', scope['region'])
    tid = record['chat']['trace_id']
    require(isinstance(tid,str) and re.fullmatch('[a-f0-9]{32}',tid) is not None)
    require(record['trace']['id'] == tid and trace['trace_id'] == tid)
    project = trace['project_id']
    require(isinstance(project,str) and re.fullmatch('[A-Za-z0-9_-]{1,128}',project) is not None)
    observed = datetime.fromtimestamp(record['observed_at_unix'], timezone.utc)
    # Collection time and execution time are separate. Neither proves current app health.
    checked = datetime.fromisoformat(trace['checked_at'].replace('Z','+00:00'))
    require(checked.tzinfo is not None and checked >= observed)
    for rows, live in ((record['trace']['observations'], False), (trace['observations'], True)):
        require(isinstance(rows,list) and 3 <= len(rows) <= 100)
        if live:
            require(all(r['trace_id'] == tid and r['project_id'] == project for r in rows))
        for name, kind in NAMES.items():
            require(any(r['name'] == name and r['type'] == kind and r['input_present'] is True
                        and r['output_present'] is True for r in rows))
    u = urlsplit(base)
    require(u.scheme in {'http','https'} and bool(u.hostname) and not u.username and not u.password
            and not u.query and not u.fragment and u.path in {'','/'} and u.port != 0)
    url = base.rstrip('/') + '/project/' + project + '/traces/' + tid
    source_hash = sha(json.dumps(record,sort_keys=True).encode())
    result = {'scope':scope, 'name':f'Hello Agent · {version} · OCI 검증 Job',
            'exportedAt':datetime.now(timezone.utc).isoformat(),
            'specText':'이 과거 실행 기록에는 명세·소스·이미지 해시 연결이 없습니다. 현재 저장소 명세가 당시 배포에 포함되었다고 판정하지 않습니다.',
            'stages':[
                {'title':'요구 명세·패키지','status':'과거 실행물과 미연결','detail':'현재 소스나 출장비 A·B 패키지를 이 실행의 근거로 사용하지 않습니다.','digest':None,'url':None},
                {'title':'업무 검증','status':'기록된 PASS · Job 완료','detail':f'{observed.isoformat()} · {delivery["job_name"]} · Job UID {delivery["job_uid"]}. 인증·모델·도구·관측 검사 통과. 아래 해시는 원본 기록 JSON의 정규화 SHA-256입니다.','digest':source_hash,'url':None},
                {'title':'앱 버전','status':version,'detail':'같은 검증의 health와 채팅 응답 버전이 일치합니다. 버전 문자열만으로 소스나 이미지 digest 일치를 증명하지 않습니다.','digest':None,'url':None},
                {'title':'OCI 배포','status':'조회 기록 SUCCEEDED','detail':f'배포 ID {run}. 검증 기록과 OCI 조회의 ID·구획·리전이 일치합니다. 현재 앱 정상 동작을 뜻하지 않습니다.','digest':None,'url':f'/deployments/runs?pipeline={pipeline}&run={run}'},
                {'title':'Langfuse 실행 추적','status':'같은 trace 관측 확인','detail':f'{checked.isoformat()} 조회 · trace {tid} · 프로젝트 {project}. AGENT·GENERATION·TOOL 입력·출력 존재 확인.','digest':None,'url':url}
            ]}
    return attach(result,record,trace,identity,evidence,root)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('record','deployment','trace','scope-file','output'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--langfuse-url',required=True)
    p.add_argument('--append-to',type=Path,help='Existing schemaVersion 1 snapshot; output must be a new file')
    p.add_argument('--release-identity',type=Path)
    p.add_argument('--release-evidence',type=Path)
    p.add_argument('--source-root',type=Path)
    a=p.parse_args()
    try:
        result=entry(read(a.record),read(a.deployment),read(a.trace),read(a.scope_file),a.langfuse_url,
                     identity=read(a.release_identity) if a.release_identity else None,
                     evidence=a.release_evidence.read_bytes() if a.release_evidence else None,root=a.source_root)
        document=read(a.append_to) if a.append_to else {'schemaVersion':1,'entries':[]}
        require(document['schemaVersion']==1 and isinstance(document['entries'],list))
        require(not any(e['scope']==result['scope'] and e['name']==result['name'] for e in document['entries']))
        document['entries'].append(result)
        write_new(a.output,document)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError):
        p.exit(1,'Check snapshot identity, completed checks, scope, URL and a new output path.\n')
    print(json.dumps({'status':'EXPORTED','entries':len(document['entries']),
                      'release_status':result['stages'][0]['status'],
                      'release_matched':result['stages'][0]['status']=='명세·소스·검증 일치',
                      'new_cloud_execution':False},ensure_ascii=False))

if __name__=='__main__':
    main()
