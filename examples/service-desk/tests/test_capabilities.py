from unittest.mock import Mock

from fastapi.testclient import TestClient
from service_desk.app import create_app
from test_journey import ACCOUNTS, headers


def test_capabilities_require_auth_and_report_missing_features(tmp_path, monkeypatch):
    monkeypatch.delenv('DESK_MEMORY_CONFIG', raising=False)
    app = create_app(database_url='sqlite:///' + str(tmp_path / 'desk.db'), accounts=ACCOUNTS)
    with TestClient(app) as client:
        assert client.get('/api/capabilities').status_code == 401
        response = client.get('/api/capabilities', headers=headers())
        assert response.status_code == 200
        data = response.json()
        assert data['app_version'] == client.get('/health').json()['version'] == '0.5.0'
        assert data['schema_version'] == 1
        capabilities = data['capabilities']
        assert len(capabilities) == 9
        assert capabilities['memory']['status'] == 'not_configured'
        assert capabilities['memory']['health'] == 'not_checked'
        assert capabilities['browser']['status'] == 'not_implemented'
        assert capabilities['code_interpreter']['status'] == 'not_implemented'
        assert capabilities['evaluations']['status'] == 'not_implemented'
        assert capabilities['identity']['mode'] == 'demo_token'
        assert 'password' not in response.text


def test_configured_memory_is_not_claimed_healthy(tmp_path):
    memory = Mock()
    app = create_app(database_url='sqlite:///' + str(tmp_path / 'desk.db'), accounts=ACCOUNTS, memory_store=memory)
    with TestClient(app) as client:
        state = client.get('/api/capabilities', headers=headers()).json()['capabilities']['memory']
        assert state['status'] == 'configured'
        assert state['health'] == 'not_checked'
        assert memory.mock_calls == []
