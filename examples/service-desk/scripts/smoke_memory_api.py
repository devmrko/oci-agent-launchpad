"""Run save, restart externally, then verify against the actual HTTP service."""
import json,sys,os
from pathlib import Path
import httpx

root=Path('/var/lib/launchpad/.run')
token=next(iter(json.loads((root/'demo-accounts.json').read_text())))
with httpx.Client(base_url='http://127.0.0.1:8092',headers={'Authorization':'Bearer '+token},timeout=45) as c:
    assert c.get('/health').json()['version']=='0.3.0'
    if sys.argv[1]=='save':
        r=c.post('/api/memories',json={'text':'[Synthetic] I prefer concise Korean explanations for VPN troubleshooting.'})
        r.raise_for_status();item=r.json()['items'][0]
        with os.fdopen(os.open(root/'memory-smoke.json',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:json.dump({'id':item['id']},f)
        print('MEMORY_HTTP_SAVE_PASS')
    else:
        expected=json.loads((root/'memory-smoke.json').read_text())['id']
        r=c.post('/api/memories/search',json={'query':'VPN help language preference'})
        r.raise_for_status();assert expected in [x['id'] for x in r.json()['items']]
        traces=c.get('/api/traces').json()
        assert any(t.get('operation')=='memory-search' and t['status']=='ok' for t in traces)
        assert 'concise Korean explanations' not in json.dumps(traces)
        print('MEMORY_HTTP_RESTART_SEARCH_TRACE_PASS')
