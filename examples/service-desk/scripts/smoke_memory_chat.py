"""Verify explicit chat memory across sessions against actual Oracle memory."""
import json, os
from pathlib import Path
from uuid import uuid4
import httpx

expected_version=os.environ.get('EXPECTED_VERSION','0.4.1')
token=next(iter(json.loads(Path('/var/lib/launchpad/.run/demo-accounts.json').read_text())))
with httpx.Client(base_url='http://127.0.0.1:8092',headers={'Authorization':'Bearer '+token},timeout=45) as c:
    assert c.get('/health').json()['version']==expected_version
    sid=c.post('/api/sessions').json()['session_id']
    label='synthetic-'+str(uuid4())
    saved=c.post('/api/chat',json={'session_id':sid,'message':'기억해 주세요: '+label+' VPN 안내는 짧은 한국어 설명을 선호합니다.'})
    saved.raise_for_status();memory_id=saved.json()['memories'][0]['id']
    assert saved.json()['trace']['tools'][0]['tool']=='memory-save'
    second=c.post('/api/sessions').json()['session_id']
    found=c.post('/api/chat',json={'session_id':second,'message':'기억에서 찾아 주세요: '+label+' VPN 설명 선호'})
    found.raise_for_status()
    assert memory_id in [x['id'] for x in found.json()['memories']]
    assert found.json()['proposal_id'] is None
    assert found.json()['trace']['tools'][0]['tool']=='memory-search'
    assert label not in json.dumps(c.get('/api/traces').json())
    print(json.dumps({'result':'PASS','version':expected_version,'checks':['chat-explicit-save','new-session-recall','source-id','no-proposal','trace-redaction']}))
