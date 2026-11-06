"""Check a deployed synthetic service desk through its public HTTP contract."""
import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check(base_url, token, version, memory=False, model=False):
    checks = []
    with httpx.Client(base_url=base_url, timeout=45, follow_redirects=False) as client:
        health = client.get('/health')
        health.raise_for_status()
        require(health.json().get('status') == 'UP' and health.json().get('version') == version,
                'Unexpected health or deployed version')
        checks.append('health-version')
        require(client.get('/api/capabilities').status_code == 401, 'Unauthenticated capability request was not rejected')
        client.headers['Authorization'] = 'Bearer ' + token

        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        report = call('GET', '/api/capabilities')
        require(report.get('schema_version') == 1 and report.get('app_version') == version,
                'Unexpected capability contract')
        expected = {'runtime','memory','gateway','identity','policy','observability','evaluations','code_interpreter','browser'}
        require(set(report.get('capabilities', {})) == expected, 'Unexpected capability set')
        checks.append('authenticated-capabilities')
        if model:
            session = call('POST', '/api/sessions')['session_id']
            response = call('POST', '/api/chat', json={'session_id': session, 'message': 'VPN 규정'})
            trace = response.get('trace', {})
            require(response.get('sources') == ['POL-VPN-01'], 'Synthetic policy source missing')
            require(trace.get('app_version') == version and trace.get('model', {}).get('provider') == 'oci',
                    'OCI model or trace version missing')
            checks.append('oci-model-versioned-trace')
        if memory:
            require(report['capabilities']['memory'].get('status') == 'configured', 'Memory is not configured')
            label = 'synthetic-runtime-check-' + str(uuid4())
            first = call('POST', '/api/sessions')['session_id']
            saved = call('POST', '/api/chat', json={'session_id': first, 'message': '기억해 주세요: ' + label + ' VPN 안내는 짧은 한국어 설명을 선호합니다.'})
            identifier = saved['memories'][0]['id']
            second = call('POST', '/api/sessions')['session_id']
            found = call('POST', '/api/chat', json={'session_id': second, 'message': '기억에서 찾아 주세요: ' + label + ' VPN 설명 선호'})
            require(identifier in [item['id'] for item in found.get('memories', [])], 'Cross-session memory recall failed')
            require(found.get('proposal_id') is None, 'Memory recall unexpectedly created a proposal')
            traces = call('GET', '/api/traces')
            require(label not in json.dumps(traces), 'Memory content leaked into traces')
            for response in [saved, found]:
                trace = response.get('trace', {})
                require(trace.get('app_version') == version, 'Memory trace version mismatch')
                require(any(t.get('request_id') == trace.get('request_id') for t in traces), 'Memory trace was not persisted')
            checks.append('cross-session-memory-and-redacted-traces')
    return {'result': 'PASS', 'version': version, 'checks': checks, 'synthetic': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--token-file', type=Path, required=True, help='Existing plain-text bearer token file; never printed')
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--memory', action='store_true', help='Write one synthetic memory and verify recall in a new session')
    parser.add_argument('--model', action='store_true', help='Call the configured OCI model with a synthetic policy question')
    args = parser.parse_args()
    try:
        token = args.token_file.read_text().strip()
        require(bool(token) and '\n' not in token and '\r' not in token, 'Invalid token file')
        result = check(args.base_url, token, args.expected_version, args.memory, args.model)
    except OSError:
        result = {'result': 'FAIL', 'reason': 'Cannot read token file'}
    except httpx.ConnectError:
        result = {'result': 'FAIL', 'reason': 'Connection failed; check service address and SSH tunnel'}
    except httpx.TimeoutException:
        result = {'result': 'FAIL', 'reason': 'Request timed out; check service and dependency health'}
    except httpx.HTTPStatusError as error:
        result = {'result': 'FAIL', 'reason': 'Unexpected HTTP status', 'status': error.response.status_code}
    except (httpx.HTTPError, RuntimeError, KeyError, TypeError, ValueError) as error:
        result = {'result': 'FAIL', 'reason': str(error) if isinstance(error, RuntimeError) else 'Unexpected response contract'}
    print(json.dumps(result))
    if result['result'] != 'PASS':
        sys.exit(1)


if __name__ == '__main__':
    main()
