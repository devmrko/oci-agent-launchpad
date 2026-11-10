"""Read one existing trace from the local Langfuse validation VM; emit no secrets or I/O bodies."""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def collect(trace_id, observed_at, base, values):
    if not re.fullmatch('[a-f0-9]{32}', trace_id):
        raise ValueError('Invalid trace ID')
    u=urlsplit(base)
    if (u.scheme not in {'http','https'} or u.hostname not in {'127.0.0.1','localhost','::1'}
        or u.username or u.password or u.query or u.fragment or u.path not in {'','/'} or u.port == 0):
        raise ValueError('Collector must run on the Langfuse host using a loopback origin')
    stamp=datetime.fromtimestamp(observed_at, timezone.utc)
    auth='Basic '+base64.b64encode((values['LF_INIT_PUBLIC']+':'+values['LF_INIT_SECRET']).encode()).decode()
    client=build_opener(NoRedirect())
    def get(path):
        with client.open(Request(base.rstrip('/')+path,headers={'Authorization':auth}),timeout=20) as response:
            return json.load(response)
    projects=get('/api/public/projects')['data']
    if len(projects)!=1:
        raise ValueError('Expected one API-key project')
    project=projects[0]['id']
    query=urlencode({'traceId':trace_id,'fromStartTime':(stamp-timedelta(minutes=10)).isoformat(),
                     'toStartTime':(stamp+timedelta(minutes=10)).isoformat(),'fields':'core,basic,io','limit':100})
    rows=get('/api/public/v2/observations?'+query)['data']
    if len(rows)>=100:
        raise ValueError('Trace exceeds bounded collector limit')
    if any(r['traceId']!=trace_id or r.get('projectId',project)!=project for r in rows):
        raise ValueError('API returned different trace or project')
    return {'project_id':project,'trace_id':trace_id,'checked_at':datetime.now(timezone.utc).isoformat(),
            'observations':[{'trace_id':r['traceId'],'project_id':project,'name':r['name'],'type':r['type'],
                             'input_present':r.get('input') is not None,'output_present':r.get('output') is not None} for r in rows]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace-id',required=True)
    p.add_argument('--observed-at',required=True,type=int)
    p.add_argument('--url',default='http://127.0.0.1:3000')
    p.add_argument('--env-file',type=Path,default=Path('.env'))
    a=p.parse_args()
    try:
        values=dict(line.split('=',1) for line in a.env_file.read_text().splitlines() if line and not line.startswith('#'))
        result=collect(a.trace_id,a.observed_at,a.url,values)
    except Exception as error:
        # Never print response bodies, credential values or exception text.
        p.exit(1,json.dumps({'status':'FAILED','error_type':type(error).__name__})+'\n')
    print(json.dumps(result))

if __name__=='__main__':
    main()
