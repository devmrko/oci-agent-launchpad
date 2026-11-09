from fastapi.testclient import TestClient
from hello_web import create_app
TOKEN = "synthetic-test-token-" + "x" * 32

def test_web_and_auth_and_tool():
    calls=[]
    def planner(message):
        calls.append(message)
        return '{"tool":"get_time","arguments":{"city":"서울"}}'
    with TestClient(create_app(token=TOKEN, planner=planner)) as client:
        assert client.get('/health').json()['status']=='UP'
        assert client.get('/').status_code==200
        assert client.post('/api/chat',json={'message':'서울 시간'}).status_code in (401,403)
        assert calls==[]
        response=client.post('/api/chat',headers={'Authorization':'Bearer '+TOKEN},json={'message':'서울 시간'})
        assert response.status_code==200,response.text
        data=response.json()
        assert data['tool_result']['timezone']=='Asia/Seoul'
        assert data['telemetry']=='disabled'
        assert len(data['trace_id'])==32

def test_bad_plan_fails_closed():
    with TestClient(create_app(token=TOKEN,planner=lambda _: '{"tool":"shell","arguments":{}}')) as client:
        assert client.post('/api/chat',headers={'Authorization':'Bearer '+TOKEN},json={'message':'실행'}).status_code==502
