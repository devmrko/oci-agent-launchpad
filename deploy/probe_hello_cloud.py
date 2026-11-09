"""Run inside OCI: check the deployed app and publish secret-free evidence.

Uses a mounted synthetic-demo credential and Langfuse project keys. Never prints
credentials or exception text. Object Storage destination is supplied by operators.
"""
import json
import os
from pathlib import Path
import time
from datetime import datetime, timedelta, timezone
import httpx
import oci


def probe():
    p = Path('/run/hello')
    token = next(iter(json.loads((p / 'accounts.json').read_text())))
    lf_url = (p / 'lf-url').read_text().strip().rstrip('/')
    auth = ((p / 'lf-public').read_text().strip(), (p / 'lf-secret').read_text().strip())
    result = {'status': 'FAILED', 'execution_location': 'OKE', 'browser_verified': False, 'checks': {}}
    try:
        with httpx.Client(timeout=90, trust_env=False) as client:
            base = os.environ['HELLO_PROBE_URL'].rstrip('/')
            health = client.get(base + '/health'); health.raise_for_status()
            result['health'] = health.json()
            result['checks']['health'] = result['health'].get('agent_id') == 'hello-agent'
            unauthorized = client.post(base + '/api/chat', json={'message': '지금 서울 몇 시인가요?'})
            result['checks']['authentication'] = unauthorized.status_code in (401, 403)
            response = client.post(base + '/api/chat', headers={'Authorization': 'Bearer ' + token}, json={'message': '지금 서울 몇 시인가요?'})
            result['chat_http_status'] = response.status_code
            response.raise_for_status(); data = response.json(); result['chat'] = data
            result['checks']['model_and_tool'] = data['mode'] == 'oci' and data['decision'] == {'tool': 'get_time', 'arguments': {'city': '서울'}} and bool(data['tool_result']['time'])
            result['checks']['telemetry_export'] = data['telemetry'] == 'exported'
            now = datetime.now(timezone.utc)
            params = {'traceId': data['trace_id'], 'fromStartTime': (now-timedelta(minutes=5)).isoformat(), 'toStartTime': (now+timedelta(minutes=5)).isoformat(), 'fields': 'core,basic,io', 'limit': 100}
            for attempt in range(18):
                trace = client.get(lf_url + '/api/public/v2/observations', params=params, auth=auth)
                result['langfuse_http_status'] = trace.status_code
                if trace.status_code == 200:
                    t = trace.json(); obs = t.get('data', [])
                    if len(obs) >= 3:
                        result['trace'] = {'id': data['trace_id'], 'observations': [{'name': x.get('name'), 'type': x.get('type'), 'input_present': x.get('input') is not None, 'output_present': x.get('output') is not None} for x in obs]}
                        result['checks']['langfuse_input_output'] = all(any(x['name'] == name and x['input_present'] and x['output_present'] for x in result['trace']['observations']) for name in ('hello-agent.chat', 'oci.model', 'get_time'))
                        break
                time.sleep(5)
            result['checks'].setdefault('langfuse_input_output', False)
            if all(result['checks'].values()): result['status'] = 'PASS'
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    result['observed_at_unix'] = int(time.time())
    return result


def main():
    output = os.environ.get('HELLO_PROBE_OUTPUT', 'object-storage')
    if output not in ('object-storage', 'stdout'): raise ValueError('Unsupported probe output')
    result = probe()
    if output == 'object-storage':
        signer = oci.auth.signers.get_oke_workload_identity_resource_principal_signer()
        storage = oci.object_storage.ObjectStorageClient({'region': os.environ['OCI_REGION']}, signer=signer)
        storage.put_object(os.environ['RESULT_NAMESPACE'], os.environ['RESULT_BUCKET'], os.environ['RESULT_OBJECT'], json.dumps(result, ensure_ascii=False).encode(), content_type='application/json')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if result['status'] != 'PASS': raise SystemExit(1)

if __name__ == '__main__': main()
