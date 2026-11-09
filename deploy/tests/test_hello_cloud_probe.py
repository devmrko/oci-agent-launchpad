import importlib.util
import json
from pathlib import Path
import httpx

spec = importlib.util.spec_from_file_location('hello_probe', Path(__file__).parents[1] / 'probe_hello_cloud.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_cloud_probe_uses_v4_observations_with_io(tmp_path, monkeypatch):
    for name, content in {'accounts.json': json.dumps({'synthetic-token': {}}), 'lf-url': 'http://langfuse.test', 'lf-public': 'public', 'lf-secret': 'secret'}.items():
        (tmp_path / name).write_text(content)
    monkeypatch.setattr(m, 'Path', lambda _: tmp_path)
    monkeypatch.setenv('HELLO_PROBE_URL', 'http://hello.test')
    def handler(request):
        if request.url.path == '/health':
            return httpx.Response(200, json={'agent_id': 'hello-agent'})
        if request.url.path == '/api/chat':
            if not request.headers.get('authorization'): return httpx.Response(401)
            return httpx.Response(200, json={'mode': 'oci', 'decision': {'tool': 'get_time', 'arguments': {'city': '서울'}}, 'tool_result': {'time': 'synthetic-time'}, 'trace_id': 'a' * 32, 'telemetry': 'exported'})
        assert request.url.path == '/api/public/v2/observations'
        assert request.url.params['fields'] == 'core,basic,io'
        assert request.url.params['traceId'] == 'a' * 32
        assert 'fromStartTime' in request.url.params and 'toStartTime' in request.url.params
        return httpx.Response(200, json={'data': [{'name': n, 'input': {}, 'output': {}, 'type': 'SPAN'} for n in ('hello-agent.chat', 'oci.model', 'get_time')]})
    client = httpx.Client
    monkeypatch.setattr(m.httpx, 'Client', lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))
    result = m.probe()
    assert result['status'] == 'PASS'
    assert result['browser_verified'] is False
    assert all(result['checks'].values())


def test_stdout_probe_needs_no_object_storage_identity(monkeypatch, capsys):
    monkeypatch.setenv('HELLO_PROBE_OUTPUT', 'stdout')
    monkeypatch.setattr(m, 'probe', lambda: {'status': 'PASS'})
    def forbidden(): raise AssertionError('Storage signer must not be used')
    monkeypatch.setattr(m.oci.auth.signers, 'get_oke_workload_identity_resource_principal_signer', forbidden)
    m.main()
    assert json.loads(capsys.readouterr().out) == {'status': 'PASS'}


def test_failed_probe_exits_nonzero(monkeypatch, capsys):
    import pytest
    monkeypatch.setenv('HELLO_PROBE_OUTPUT', 'stdout')
    monkeypatch.setattr(m, 'probe', lambda: {'status': 'FAILED'})
    with pytest.raises(SystemExit) as error: m.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'FAILED'
