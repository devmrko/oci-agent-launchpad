import json
from pathlib import Path
import sys
import httpx
import pytest
sys.path.insert(0, str(Path(__file__).parents[2] / 'examples/service-desk/scripts'))
from check_deployment import observations, verify_observations


def records():
    return [{'id':str(i), 'name':name, 'traceId':'t'+request,
             'metadata':{'request_id':request}, 'input': 'VPN 규정' if i==0 else None,
             'output':'answer' if i==0 else None}
            for i,(name,request) in enumerate([('service-desk.chat','c'),('model.route','c'),
                ('tool.search','c'),('service-desk.memory-search','m'),('tool.memory-search','m')])]


def test_empty_page_cursor_and_later_page_are_followed():
    calls=[]
    def handle(request):
        calls.append(dict(request.url.params))
        if len(calls)==1:return httpx.Response(200,json={'data':[],'meta':{'cursor':'next'}})
        return httpx.Response(200,json={'data':records(),'meta':{'cursor':None}})
    with httpx.Client(base_url='https://lf.test',transport=httpx.MockTransport(handle)) as client:
        rows=observations(client,'start','end',{'c','m'},3)
    assert calls[1]['cursor']=='next'
    assert calls[0]['fromStartTime']==calls[1]['fromStartTime']=='start'
    assert verify_observations(rows,'c','m')['observations']==5


@pytest.mark.parametrize('mode', ['cycle','limit','bad-page','unauthorized'])
def test_incomplete_scan_fails(mode):
    def handle(request):
        if mode=='unauthorized':return httpx.Response(401,json={'error':'secret should not be output'})
        if mode=='bad-page':return httpx.Response(200,json={'data':[]})
        cursor='fixed' if mode=='cycle' else request.url.params.get('cursor','')+'x'
        return httpx.Response(200,json={'data':[],'meta':{'cursor':cursor}})
    with httpx.Client(base_url='https://lf.test',transport=httpx.MockTransport(handle)) as client:
        with pytest.raises((RuntimeError,httpx.HTTPStatusError)):
            observations(client,'s','e',{'c','m'},3)


@pytest.mark.parametrize('mode',['missing','leaked','no-input','no-output','error','wrong-name'])
def test_bad_observations_cannot_pass(mode):
    items=records()
    if mode=='missing':items.pop()
    elif mode=='leaked':items[-1]['input']='private memory'
    elif mode=='no-input':items[0]['input']=None
    elif mode=='no-output':items[0]['output']=None
    elif mode=='error':items[1]['level']='ERROR'
    elif mode=='wrong-name':items[-1]['name']='unrelated'
    with pytest.raises(RuntimeError):verify_observations(items,'c','m')


def test_cli_failure_does_not_print_credentials(monkeypatch,capsys):
    import io
    import check_deployment as module
    monkeypatch.setattr(sys,'argv',['check','--base-url','https://app.test','--expected-version','0.5.0','--credentials-stdin'])
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps({'token':'SECRET_VALUE','langfuse':{}})))
    def fail(*args):
        raise httpx.ConnectError('internal SECRET_VALUE')
    monkeypatch.setattr(module,'run',fail)
    assert module.main()==1
    output=capsys.readouterr().out
    assert 'SECRET_VALUE' not in output
    assert json.loads(output)['result']=='FAIL'


def test_run_correlates_actual_http_request_ids(monkeypatch):
    import check_deployment as module
    calls=[]
    def runtime(url, token, version, **options):
        assert options=={'memory':True,'model':True}
        return {'result':'PASS','version':version}
    monkeypatch.setattr(module,'check',runtime)
    def handler(request):
        calls.append((request.url.host,request.url.path))
        if request.url.host=='app.test':
            assert request.headers['authorization']=='Bearer token'
            if request.url.path=='/api/sessions':return httpx.Response(200,json={'session_id':'session'})
            if request.url.path=='/api/chat':
                assert json.loads(request.content)['session_id']=='session'
                return httpx.Response(200,json={'trace':{'request_id':'c'}})
            return httpx.Response(200,json={'items':[]},headers={'x-request-id':'m'})
        assert request.url.params['fields']=='core,basic,io,metadata'
        assert request.headers['authorization'].startswith('Basic ')
        return httpx.Response(200,json={'data':records(),'meta':{'cursor':None}})
    original=httpx.Client
    monkeypatch.setattr(module.httpx,'Client',lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(handler)))
    result=module.run('https://app.test','token','0.5.0',{'url':'https://lf.test','public_key':'p','secret_key':'s'},attempts=1)
    assert result['telemetry']['observations']==5
    assert calls==[('app.test','/api/sessions'),('app.test','/api/chat'),('app.test','/api/memories/search'),('lf.test','/api/public/v2/observations')]
