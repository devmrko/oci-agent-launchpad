"""Local wiring tests: API -> real exporter payload; no OCI or Langfuse calls."""
import hashlib
import json
from pathlib import Path
import shutil
import httpx
import pytest
from fastapi.testclient import TestClient
import hello_release
import hello_telemetry
from hello_web import create_app

TOKEN='synthetic-release-test-'+('x'*32)


def identity():
    root=Path(hello_release.__file__).resolve().parent
    files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in hello_release.RUNTIME_FILES}
    result={'schema_version':1,'agent_id':'hello-agent','app_version':'0.1.0','runtime_files':files,
            'spec_sha256':'a'*64,'source_sha256':hello_release.digest(files),'test_evidence_sha256':'b'*64}
    result['release_id']=hello_release.digest(result)
    return result


def test_identity_reaches_health_chat_and_every_otlp_span(monkeypatch):
    value=identity(); monkeypatch.setenv('HELLO_RELEASE_IDENTITY',json.dumps(value))
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        assert request.url.path=='/api/public/otel/v1/traces'
        return httpx.Response(200,json={})
    client=httpx.Client
    monkeypatch.setattr(hello_telemetry.httpx,'Client',lambda **kw: client(transport=httpx.MockTransport(handler),**kw))
    app=create_app(token=TOKEN,planner=lambda _: '{"tool":"get_time","arguments":{"city":"서울"}}',
                   telemetry={'url':'http://local-test.invalid','public_key':'synthetic-public','secret_key':'synthetic-secret'})
    with TestClient(app) as web:
        health=web.get('/health').json()
        response=web.post('/api/chat',headers={'Authorization':'Bearer '+TOKEN},json={'message':'서울 시간'})
        assert response.status_code==200
        data=response.json()
        assert data['telemetry']=='exported'
        expected={k:value[k] for k in hello_release.SUMMARY}
        assert health['release']==data['release']==expected
        spans=requests[0]['resourceSpans'][0]['scopeSpans'][0]['spans']
        assert {s['name'] for s in spans}=={'hello-agent.chat','oci.model','get_time'}
        for span in spans:
            attrs={a['key']:a['value']['stringValue'] for a in span['attributes']}
            for key,value in expected.items():
                assert attrs['langfuse.observation.metadata.'+key]==value
            assert span['traceId']==data['trace_id']
        injected=web.post('/api/chat',headers={'Authorization':'Bearer '+TOKEN},json={'message':'서울 시간','release':expected})
        assert injected.status_code==400  # Foundation's validation-error response.
        assert len(requests)==1


def test_source_tamper_prevents_app_start(tmp_path,monkeypatch):
    value=identity(); source=Path(hello_release.__file__).parent
    for name in hello_release.RUNTIME_FILES: shutil.copyfile(source/name,tmp_path/name)
    monkeypatch.setenv('HELLO_RELEASE_IDENTITY',json.dumps(value))
    monkeypatch.setattr(hello_release,'__file__',str(tmp_path/'hello_release.py'))
    (tmp_path/'agent.py').write_text('# changed after validation\n')
    with pytest.raises(ValueError,match='does not match installed files'):
        create_app(token=TOKEN)


def test_invalid_identity_does_not_silently_disable_check(monkeypatch):
    value=identity(); value['spec_sha256']='c'*64
    for raw in ('{}','not json',json.dumps(value)):
        monkeypatch.setenv('HELLO_RELEASE_IDENTITY',raw)
        with pytest.raises(ValueError): create_app(token=TOKEN)


def test_existing_app_without_identity_is_explicit(monkeypatch):
    monkeypatch.delenv('HELLO_RELEASE_IDENTITY',raising=False)
    with TestClient(create_app(token=TOKEN)) as web:
        assert web.get('/health').json()['release'] is None


def test_actual_payload_through_collector_and_companion_export(tmp_path,monkeypatch):
    import sys
    root=Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root/'scripts'))
    from command_evidence import execute
    from build_hello_identity import prepare
    import collect_langfuse_evidence as collector
    from export_cloud_evidence import entry
    evidence=tmp_path/'command.json'
    # Synthetic unit fixture, not a claim that this command verifies application behavior.
    execute(root,'specs/hello-release-identity/checks.json',evidence,[sys.executable,'-c','pass'])
    value=prepare(root,evidence,tmp_path/'identity.json')
    monkeypatch.setenv('HELLO_RELEASE_IDENTITY',json.dumps(value))
    payloads=[]
    def handler(request):
        payloads.append(json.loads(request.content));return httpx.Response(200,json={})
    client=httpx.Client
    monkeypatch.setattr(hello_telemetry.httpx,'Client',lambda **kw: client(transport=httpx.MockTransport(handler),**kw))
    app=create_app(token=TOKEN,planner=lambda _: '{"tool":"get_time","arguments":{"city":"서울"}}',
                   telemetry={'url':'http://local-test.invalid','public_key':'test','secret_key':'test'})
    record=json.loads((root/'examples/hello-agent/verification/companion-job-2026-11-09.json').read_text())
    with TestClient(app) as web:
        record['health']=web.get('/health').json()
        record['chat']=web.post('/api/chat',headers={'Authorization':'Bearer '+TOKEN},json={'message':'서울 시간'}).json()
    tid=record['chat']['trace_id'];record['trace']['id']=tid
    rows=[]
    for span in payloads[0]['resourceSpans'][0]['scopeSpans'][0]['spans']:
        attrs={a['key']:a['value']['stringValue'] for a in span['attributes']}
        rows.append({'traceId':span['traceId'],'projectId':'test','name':span['name'],
                     'type':attrs['langfuse.observation.type'].upper(),
                     'input':json.loads(attrs['langfuse.observation.input']),
                     'output':json.loads(attrs['langfuse.observation.output']),
                     'metadata':{key.removeprefix('langfuse.observation.metadata.'):v for key,v in attrs.items()
                                 if key.startswith('langfuse.observation.metadata.')}})
    class Response:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps(self.data).encode()
    class Client:
        def open(self,request,timeout):
            if '/projects' in request.full_url:return Response({'data':[{'id':'test'}]})
            assert 'metadata' in request.full_url
            return Response({'data':rows})
    monkeypatch.setattr(collector,'build_opener',lambda *args:Client())
    trace=collector.collect(tid,record['observed_at_unix'],'http://localhost:3000',{'LF_INIT_PUBLIC':'test','LF_INIT_SECRET':'test'})
    deployment={'data':{'id':record['delivery']['deployment_id'],'compartment-id':'test','lifecycle-state':'SUCCEEDED',
                       'deploy-pipeline-id':'ocid1.devopsdeploypipeline.oc1.ap-seoul-1.test'}}
    scope=dict(profile='TEST',tenancy='test',user='test',demo=False,region='ap-seoul-1',compartment='test')
    result=entry(record,deployment,trace,scope,'http://localhost:18080',identity=value,evidence=evidence.read_bytes(),root=root)
    assert result['stages'][0]['status']=='명세·소스·검증 일치'
    assert result['stages'][0]['digest']==value['release_id']
    assert result['specText']==(root/'specs/hello-agent/spec.md').read_text()
    rows[1]['metadata']['release_id']='0'*64
    trace=collector.collect(tid,record['observed_at_unix'],'http://localhost:3000',{'LF_INIT_PUBLIC':'test','LF_INIT_SECRET':'test'})
    result=entry(record,deployment,trace,scope,'http://localhost:18080',identity=value,evidence=evidence.read_bytes(),root=root)
    assert result['stages'][0]['status']=='릴리스 불일치'
    assert len(result['stages'])==5
