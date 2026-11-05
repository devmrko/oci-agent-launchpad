from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from python_foundation.errors import BusinessError

from service_desk.app import create_app
from service_desk.planning import OciPlanner


class Client:
    def __init__(self, content, finish="stop"):
        self.content, self.finish = content, finish
        self.calls = 0

    def chat(self, request):
        self.calls += 1
        assert request.chat_request.max_tokens == 128
        return SimpleNamespace(
            data=SimpleNamespace(
                chat_response={
                    "choices": [
                        {
                            "finish_reason": self.finish,
                            "message": {"content": [{"type": "TEXT", "text": self.content}]},
                        }
                    ],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 5},
                }
            )
        )


def test_real_adapter_contract_and_gateway_events(tmp_path):
    provider = Client('{"action":"propose"}')
    planner = OciPlanner(region="us-ashburn-1", compartment="test-compartment", client=provider)
    accounts = {
        "a" * 32: {"subject": "alice", "can_write": True},
        "b" * 32: {"subject": "bob", "can_write": True},
    }
    auth = {"Authorization": "Bearer " + "a" * 32}
    with TestClient(
        create_app(database_url="sqlite:///" + str(tmp_path / "db"), accounts=accounts, planner=planner)
    ) as client:
        sid = client.post("/api/sessions", headers=auth).json()["session_id"]
        denied = client.post(
            "/api/chat",
            headers={"Authorization": "Bearer " + "b" * 32},
            json={"session_id": sid, "message": "secret"},
        )
        assert denied.status_code == 403
        assert provider.calls == 0
        response = client.post(
            "/api/chat", headers=auth, json={"session_id": sid, "message": "지원 요청 접수"}
        )
        assert response.status_code == 200, response.text
        trace = response.json()["trace"]
        assert trace["mode"] == "live-model"
        assert trace["model"]["input_tokens"] == 30
        assert trace["model"]["region"] == "us-ashburn-1"
        assert trace["tools"][0]["tool"] == "propose"
        assert trace["tools"][0]["run_id"] == response.headers["x-request-id"]
        assert client.get("/api/tickets", headers=auth).json() == []
        assert {x["name"] for x in client.get("/api/tools", headers=auth).json()} == {
            "search",
            "propose",
            "approve",
        }


@pytest.mark.parametrize(
    "text,finish",
    [
        ('{"action":"approve"}', "stop"),
        ('{"action":"search","token":"secret"}', "stop"),
        ('{"action":"search"}', "max_tokens"),
        ("not-json", "stop"),
    ],
)
def test_invalid_model_output_never_becomes_a_tool_call(text, finish):
    planner = OciPlanner(region="us-ashburn-1", compartment="test", client=Client(text, finish))
    with pytest.raises(BusinessError) as error:
        planner("synthetic input")
    assert error.value.error.code == "MODEL_UNAVAILABLE"
    assert "secret" not in str(error.value)
