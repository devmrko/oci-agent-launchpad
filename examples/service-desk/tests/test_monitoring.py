from fastapi.testclient import TestClient
from test_journey import app_for, headers, proposal


def test_monitoring_pages_filters_owner_and_snapshot(tmp_path):
    with TestClient(app_for(tmp_path/'desk.db')) as c:
        base='/api/monitoring/v1'
        assert c.get(base+'/agents').status_code==401
        assert c.get(base+'/agents',headers=headers()).json()['items'][0]['id']=='service-desk'
        url=base+'/agents/service-desk/executions'
        for _ in range(5):proposal(c)
        first=c.get(url,headers=headers(),params={'page_size':2}).json()
        assert first['total']==5 and first['pages']==3 and len(first['items'])==2
        proposal(c)
        second=c.get(url,headers=headers(),params={'page_size':2,'page':2,'snapshot':first['snapshot']}).json()
        assert second['total']==5
        assert not set(x['id'] for x in first['items']) & set(x['id'] for x in second['items'])
        assert c.get(url,headers=headers('b')).json()['total']==0
        item=first['items'][0]
        assert item['timestamp'] and item['level']=='INFO' and item['operation']=='chat'
        assert c.get(url+'/'+item['id'],headers=headers('b')).status_code==404
        detail=c.get(url+'/'+item['id'],headers=headers()).json()['item']
        assert detail['session_id'] and detail['tools'] and 'message' not in detail
        assert c.get(url,headers=headers(),params={'session_id':detail['session_id']}).json()['total']==1
        assert c.get(url,headers=headers(),params={'level':'ERROR'}).json()['total']==0
        invalid=c.get(url,headers=headers(),params={'page_size':101})
        assert invalid.status_code==400
        assert 'VALIDATION_FAILED' in invalid.text
        assert c.get(url,headers=headers(),params={'since':'yesterday'}).status_code==422
        assert c.get(base+'/agents/other/executions',headers=headers()).status_code==404


def test_failure_detail_has_code_without_raw_prompt(tmp_path):
    with TestClient(app_for(tmp_path/'desk.db',planner=lambda _: (_ for _ in ()).throw(RuntimeError('private')))) as c:
        sid=c.post('/api/sessions',headers=headers()).json()['session_id']
        try:c.post('/api/chat',headers=headers(),json={'session_id':sid,'message':'secret prompt'})
        except RuntimeError:pass
        response=c.get('/api/monitoring/v1/agents/service-desk/executions',headers=headers(),params={'level':'ERROR'})
        item=response.json()['items'][0]
        assert item['session_id']==sid and item['error_code']=='RuntimeError'
        assert 'private' not in response.text and 'secret prompt' not in response.text
