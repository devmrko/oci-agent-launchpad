"""Synthetic post-deployment model, memory and Langfuse checks; writes test data."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import sys
import time

import httpx
from check_runtime import check, require


def observations(client, start, end, request_ids, max_pages):
    cursor = None
    seen = set()
    found = {}
    for _ in range(max_pages):
        params = {'fromStartTime': start, 'toStartTime': end,
                  'fields': 'core,basic,io,metadata', 'limit': 100}
        if cursor:
            params['cursor'] = cursor
        response = client.get('/api/public/v2/observations', params=params)
        response.raise_for_status()
        page = response.json()
        require(isinstance(page.get('data'), list) and isinstance(page.get('meta'), dict),
                'Invalid observation page')
        for item in page['data']:
            if item.get('metadata', {}).get('request_id') in request_ids:
                found[item['id']] = item
        cursor = page['meta'].get('cursor')
        if cursor is None or cursor == '':
            return list(found.values())
        require(isinstance(cursor, str) and cursor not in seen, 'Invalid or repeated observation cursor')
        seen.add(cursor)
    raise RuntimeError('Observation page limit reached; verification incomplete')


def verify_observations(items, chat_id, memory_id):
    chat = [x for x in items if x.get('metadata', {}).get('request_id') == chat_id]
    memory = [x for x in items if x.get('metadata', {}).get('request_id') == memory_id]
    require(len(chat) == 3 and {x['name'] for x in chat} == {'service-desk.chat', 'model.route', 'tool.search'},
            'Expected chat observations missing or duplicated')
    require(len(memory) == 2 and {x['name'] for x in memory} == {'service-desk.memory-search', 'tool.memory-search'},
            'Expected memory observations missing or duplicated')
    require(all(x.get('level') != 'ERROR' for x in items), 'Telemetry reported an error')
    root = next(x for x in chat if x['name'] == 'service-desk.chat')
    require('VPN' in json.dumps(root.get('input'), ensure_ascii=False) and root.get('output'),
            'Chat input/output missing; check synthetic capture_content setting')
    require(all(x.get('input') is None and x.get('output') is None for x in memory),
            'Memory body appeared in telemetry')
    return {'observations': len(items), 'chat_input_output': True, 'memory_content_excluded': True,
            'traces': sorted({x['traceId'] for x in items})}


def run(base_url, token, version, langfuse, attempts=25, interval=2, max_pages=20):
    require(1 <= attempts <= 60 and 0 <= interval <= 10 and 1 <= max_pages <= 100, 'Invalid polling limits')
    result = check(base_url, token, version, memory=True, model=True)
    start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with httpx.Client(base_url=base_url, headers={'Authorization': 'Bearer ' + token},
                      timeout=60, trust_env=False, follow_redirects=False) as client:
        response = client.post('/api/sessions'); response.raise_for_status()
        session = response.json()['session_id']
        response = client.post('/api/chat', json={'session_id': session, 'message': 'VPN 규정'})
        response.raise_for_status(); chat_id = response.json()['trace']['request_id']
        response = client.post('/api/memories/search', json={'query': 'synthetic deployment VPN preference'})
        response.raise_for_status(); memory_id = response.headers['x-request-id']
    end = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    with httpx.Client(base_url=langfuse['url'], auth=(langfuse['public_key'], langfuse['secret_key']),
                      timeout=15, trust_env=False, follow_redirects=False) as client:
        for attempt in range(attempts):
            items = observations(client, start, end, {chat_id, memory_id}, max_pages)
            if len(items) >= 5:
                report = verify_observations(items, chat_id, memory_id)
                return {**result, 'telemetry': report}
            if attempt + 1 < attempts:
                time.sleep(interval)
    raise RuntimeError('Timed out waiting for telemetry observations')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--credentials-stdin', action='store_true', required=True,
                        help='Read JSON {token,langfuse:{url,public_key,secret_key}} from stdin; never printed')
    parser.add_argument('--attempts', type=int, default=25)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--max-pages', type=int, default=20)
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(65537)
        require(len(raw) <= 65536, 'Credential input too large')
        credentials = json.loads(raw)
        token = credentials['token']
        require(isinstance(token, str) and token and not any(c.isspace() for c in token), 'Invalid token')
        result = run(args.base_url, token, args.expected_version, credentials['langfuse'],
                     args.attempts, args.interval, args.max_pages)
    except httpx.HTTPStatusError as error:
        result = {'result': 'FAIL', 'reason': 'Unexpected HTTP status', 'status': error.response.status_code}
    except RuntimeError as error:
        result = {'result': 'FAIL', 'reason': str(error)}
    except (ValueError, KeyError, TypeError, OSError, httpx.HTTPError):
        result = {'result': 'FAIL', 'reason': 'Connection, credentials or response contract invalid'}
    print(json.dumps(result))
    return 0 if result['result'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
