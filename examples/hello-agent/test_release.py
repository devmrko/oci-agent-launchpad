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
