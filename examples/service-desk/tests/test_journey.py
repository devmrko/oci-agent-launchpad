from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from service_desk.app import create_app

ACCOUNTS = {
    "a" * 32: {"subject": "alice", "can_write": True},
    "b" * 32: {"subject": "bob", "can_write": True},
    "r" * 32: {"subject": "reader", "can_write": False},
}


def headers(key="a"):
    return {"Authorization": "Bearer " + key * 32}


def app_for(path, planner=None):
    return create_app(database_url="sqlite:///" + str(path), accounts=ACCOUNTS, planner=planner)


def proposal(client, key="a"):
    sid = client.post("/api/sessions", headers=headers(key)).json()["session_id"]
    response = client.post(
        "/api/chat", headers=headers(key), json={"session_id": sid, "message": "VPN 접속 장애를 접수해주세요"}
    )
    assert response.status_code == 200, response.text
    return sid, response.json()["proposal_id"]


def test_full_journey_and_restart(tmp_path):
    db = tmp_path / "desk.db"
    with TestClient(app_for(db)) as client:
        assert client.post("/api/sessions").status_code == 401
        assert client.post("/api/sessions", headers={"Authorization": "Bearer invalid"}).status_code == 401
        sid, pid = proposal(client)
        assert client.get("/api/tickets", headers=headers()).json() == []
        result = client.post(f"/api/proposals/{pid}/approve", headers=headers(), json={"confirmed": True})
        assert result.status_code == 200, result.text
        assert result.json()["synthetic"] is True
        for _ in range(3):
            assert (
                client.post(
                    f"/api/proposals/{pid}/approve", headers=headers(), json={"confirmed": True}
                ).json()
                == result.json()
            )
        assert len(client.get("/api/tickets", headers=headers()).json()) == 1
        assert client.put("/api/memory", headers=headers(), json={"language": "en"}).status_code == 200
    with TestClient(app_for(db)) as client:
        assert len(client.get("/api/tickets", headers=headers()).json()) == 1
        assert client.get("/api/memory", headers=headers()).json() == {"language": "en"}
        assert client.get("/api/memory", headers=headers("b")).json() == {"language": None}
        assert client.delete("/api/memory", headers=headers()).status_code == 200
        assert client.get("/api/memory", headers=headers()).json() == {"language": None}
        assert (
            client.post(
                "/api/chat", headers=headers(), json={"session_id": sid, "message": "주가 예측"}
            ).json()["sources"]
            == []
        )


def test_ownership_approval_and_scope(tmp_path):
    with TestClient(app_for(tmp_path / "desk.db")) as client:
        sid, pid = proposal(client)
        assert (
            client.post(
                "/api/chat", headers=headers("b"), json={"session_id": sid, "message": "vpn"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/proposals/{pid}/approve", headers=headers("b"), json={"confirmed": True}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/proposals/{pid}/approve",
                headers=headers(),
                json={"confirmed": True, "summary": "changed"},
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/proposals/{pid}/approve", headers=headers(), json={"confirmed": False}
            ).status_code
            == 400
        )
        _, reader_pid = proposal(client, "r")
        assert (
            client.post(
                f"/api/proposals/{reader_pid}/approve", headers=headers("r"), json={"confirmed": True}
            ).status_code
            == 403
        )
        assert client.get("/api/tickets", headers=headers()).json() == []
        assert all(t["status"] == "error" for t in client.get("/api/traces", headers=headers("b")).json())


def test_trace_is_correlated_and_redacted(tmp_path):
    with TestClient(app_for(tmp_path / "desk.db")) as client:
        sid = client.post("/api/sessions", headers=headers()).json()["session_id"]
        message = "VPN private-detail-123"
        response = client.post("/api/chat", headers=headers(), json={"session_id": sid, "message": message})
        assert response.json()["sources"] == ["POL-VPN-01"]
        trace = client.get("/api/traces", headers=headers()).json()[0]
        assert trace["request_id"] == response.headers["x-request-id"]
        assert message not in str(trace)
        assert "a" * 32 not in str(trace)
        assert trace["mode"] == "deterministic-demo"


def test_untrusted_model_plan_rejected(tmp_path):
    with TestClient(app_for(tmp_path / "desk.db", planner=lambda _: "execute_shell")) as client:
        sid = client.post("/api/sessions", headers=headers()).json()["session_id"]
        response = client.post(
            "/api/chat", headers=headers(), json={"session_id": sid, "message": "anything"}
        )
        assert response.status_code == 400
        assert client.get("/api/tickets", headers=headers()).json() == []


def test_concurrent_approval_is_single_ticket(tmp_path):
    with TestClient(app_for(tmp_path / "desk.db")) as client:
        _, pid = proposal(client)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(
                    lambda _: client.post(
                        f"/api/proposals/{pid}/approve", headers=headers(), json={"confirmed": True}
                    ),
                    range(8),
                )
            )
        assert all(r.status_code == 200 for r in results), [r.text for r in results]
        assert len({r.json()["ticket_id"] for r in results}) == 1
        assert len(client.get("/api/tickets", headers=headers()).json()) == 1


def test_memory_used_in_next_session_and_failure_is_observable(tmp_path):
    with TestClient(app_for(tmp_path / "desk.db")) as client:
        client.put("/api/memory", headers=headers(), json={"language": "en"})
        sid = client.post("/api/sessions", headers=headers()).json()["session_id"]
        response = client.post("/api/chat", headers=headers(), json={"session_id": sid, "message": "vpn"})
        assert response.json()["language"] == "en"
        assert "MFA enrollment" in response.json()["answer"]
        failure = client.post("/api/chat", headers=headers("b"), json={"session_id": sid, "message": "vpn"})
        trace = client.get("/api/traces", headers=headers("b")).json()[0]
        assert trace["request_id"] == failure.headers["x-request-id"]
        assert trace["status"] == "error"
        assert trace["error_code"] == "AccessDenied"


def test_repeated_correlation_id_and_invalid_plan_type(tmp_path):
    with TestClient(app_for(tmp_path / "desk.db")) as client:
        sid = client.post("/api/sessions", headers=headers()).json()["session_id"]
        for _ in range(2):
            response = client.post(
                "/api/chat",
                headers={**headers(), "x-request-id": "repeat-id"},
                json={"session_id": sid, "message": "vpn"},
            )
            assert response.status_code == 200
        assert len(client.get("/api/traces", headers=headers()).json()) == 2
    with TestClient(app_for(tmp_path / "invalid.db", planner=lambda _: ["execute_shell"])) as client:
        sid = client.post("/api/sessions", headers=headers()).json()["session_id"]
        assert (
            client.post(
                "/api/chat", headers=headers(), json={"session_id": sid, "message": "vpn"}
            ).status_code
            == 400
        )
