"""Exercise the running local demo without printing credentials or free text."""

import json
from pathlib import Path

import httpx

token = next(iter(json.loads(Path(".run/demo-accounts.json").read_text())))
with httpx.Client(base_url="http://127.0.0.1:8092", headers={"Authorization": "Bearer " + token}) as client:

    def call(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    sid = call("POST", "/api/sessions")["session_id"]
    found = call("POST", "/api/chat", json={"session_id": sid, "message": "VPN 규정"})
    assert found["sources"] == ["POL-VPN-01"]
    before = len(call("GET", "/api/tickets"))
    draft = call("POST", "/api/chat", json={"session_id": sid, "message": "VPN 장애 접수"})
    assert len(call("GET", "/api/tickets")) == before
    path = "/api/proposals/" + draft["proposal_id"] + "/approve"
    ticket = call("POST", path, json={"confirmed": True})
    assert call("POST", path, json={"confirmed": True}) == ticket
    assert len(call("GET", "/api/tickets")) == before + 1
    traces = call("GET", "/api/traces")
    assert any(t["request_id"] == draft["trace"]["request_id"] for t in traces)
    print(
        json.dumps(
            {
                "result": "PASS",
                "checks": ["policy-source", "approval-required", "idempotency", "request-trace"],
                "mode": draft["trace"]["mode"],
            }
        )
    )
