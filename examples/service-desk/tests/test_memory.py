from unittest.mock import Mock

from fastapi.testclient import TestClient
from python_foundation.agent_memory import MemoryItem
from test_journey import ACCOUNTS, headers

from service_desk.app import create_app


def test_explicit_memory_auth_and_trace_redaction(tmp_path):
    memory = Mock()
    memory.save.return_value = MemoryItem(id="memory-1", text="synthetic-secret-note")
    memory.search.return_value = [memory.save.return_value]
    app = create_app(
        database_url="sqlite:///" + str(tmp_path / "desk.db"), accounts=ACCOUNTS, memory_store=memory
    )
    with TestClient(app) as client:
        assert client.post("/api/memories", json={"text": "note"}).status_code == 401
        assert (
            client.post(
                "/api/memories", headers=headers(), json={"text": "note", "user_id": "bob"}
            ).status_code
            == 400
        )
        response = client.post("/api/memories", headers=headers(), json={"text": "synthetic-secret-note"})
        assert response.status_code == 200
        assert memory.save.call_args.args[0].subject == "alice"
        found = client.post("/api/memories/search", headers=headers(), json={"query": "note"})
        assert found.status_code == 200
        assert found.json()["items"][0]["id"] == "memory-1"
        traces = client.get("/api/traces", headers=headers()).json()
        assert len(traces) == 2
        assert "synthetic-secret-note" not in str(traces)
        assert traces[0]["tools"][0]["tool"] == "memory-save"
