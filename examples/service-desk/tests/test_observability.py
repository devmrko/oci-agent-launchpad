import json
import httpx
from fastapi.testclient import TestClient
from service_desk.app import create_app
from service_desk.observability import ChatTelemetry

ACCOUNTS = {"a" * 32: {"subject": "observer", "can_write": True}}
HEADERS = {"Authorization": "Bearer " + "a" * 32}

def run_chat(tmp_path, telemetry):
    app = create_app(database_url="sqlite:///" + str(tmp_path / "desk.db"), accounts=ACCOUNTS, telemetry=telemetry)
    with TestClient(app) as client:
        sid = client.post("/api/sessions", headers=HEADERS).json()["session_id"]
        response = client.post("/api/chat", headers=HEADERS, json={"session_id": sid, "message": "VPN 사용 규정 알려주세요"})
        assert response.status_code == 200
        return response.json()

def test_actual_route_exports_same_input_and_answer(tmp_path):
    payloads=[]
    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={})
    telemetry=ChatTelemetry("http://localhost", "pk", "sk", capture_content=True, transport=httpx.MockTransport(handle))
    result=run_chat(tmp_path, telemetry)
    span=payloads[0]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attrs={a["key"]:a["value"]["stringValue"] for a in span["attributes"]}
    assert json.loads(attrs["langfuse.observation.input"])["message"]=="VPN 사용 규정 알려주세요"
    assert json.loads(attrs["langfuse.observation.output"])["answer"]==result["answer"]
    assert telemetry.sent==1

def test_content_is_excluded_by_default(tmp_path):
    payloads=[]
    def handle(request):
        payloads.append(request.content.decode())
        return httpx.Response(200,json={})
    telemetry=ChatTelemetry("http://localhost", "pk", "sk", transport=httpx.MockTransport(handle))
    run_chat(tmp_path,telemetry)
    assert "langfuse.observation.input" not in payloads[0]
    assert "langfuse.observation.output" not in payloads[0]
    assert "observer" not in payloads[0]

def test_export_outage_does_not_fail_chat(tmp_path):
    def handle(request):
        raise httpx.ConnectError("offline")
    telemetry=ChatTelemetry("http://localhost", "pk", "sk", capture_content=True, transport=httpx.MockTransport(handle))
    assert run_chat(tmp_path,telemetry)["answer"]
    assert telemetry.failed==1


def test_nested_live_route_and_tool_have_same_trace_and_real_output(tmp_path):
    from service_desk.planning import Decision
    payloads=[]
    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,json={})
    telemetry=ChatTelemetry("http://localhost", "pk", "sk", capture_content=True, transport=httpx.MockTransport(handle))
    app=create_app(database_url="sqlite:///"+str(tmp_path/"live.db"),accounts=ACCOUNTS,
                   planner=lambda _: Decision("search", {"model":"mock", "input_tokens":12}),telemetry=telemetry)
    with TestClient(app) as client:
        sid=client.post("/api/sessions",headers=HEADERS).json()["session_id"]
        result=client.post("/api/chat",headers=HEADERS,json={"session_id":sid,"message":"VPN 규정"}).json()
    spans=payloads[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    root,model,tool=spans
    assert [s["name"] for s in spans]==["service-desk.chat","model.route","tool.search"]
    for child in (model,tool):
        assert child["traceId"]==root["traceId"] and child["parentSpanId"]==root["spanId"]
        assert int(root["startTimeUnixNano"])<=int(child["startTimeUnixNano"])<=int(child["endTimeUnixNano"])<=int(root["endTimeUnixNano"])
    attrs={a["key"]:a["value"]["stringValue"] for a in tool["attributes"]}
    assert json.loads(attrs["langfuse.observation.output"])["answer"]==result["answer"]


def test_failed_model_is_marked_without_raw_exception_or_prompt(tmp_path):
    payloads=[]
    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,json={})
    def fail(_):
        raise RuntimeError("secret backend detail")
    telemetry=ChatTelemetry("http://localhost", "pk", "sk", capture_content=True, transport=httpx.MockTransport(handle))
    app=create_app(database_url="sqlite:///"+str(tmp_path/"failed.db"),accounts=ACCOUNTS,planner=fail,telemetry=telemetry)
    with TestClient(app,raise_server_exceptions=False) as client:
        sid=client.post("/api/sessions",headers=HEADERS).json()["session_id"]
        assert client.post("/api/chat",headers=HEADERS,json={"session_id":sid,"message":"private prompt"}).status_code==500
    spans=payloads[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans)==2 and all(s["status"]["code"]==2 for s in spans)
    serialized=json.dumps(payloads)
    assert "private prompt" not in serialized and "secret backend detail" not in serialized
    assert "tool.search" not in serialized


def test_approval_success_retry_and_denial_keep_business_rules(tmp_path):
    payloads=[]
    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,json={})
    telemetry=ChatTelemetry("http://localhost", "pk", "sk", capture_content=True, transport=httpx.MockTransport(handle))
    accounts={**ACCOUNTS, "r"*32:{"subject":"reader", "can_write":False}}
    app=create_app(database_url="sqlite:///"+str(tmp_path/"approval.db"),accounts=accounts,telemetry=telemetry)
    with TestClient(app) as client:
        sid=client.post("/api/sessions",headers=HEADERS).json()["session_id"]
        proposal=client.post("/api/chat",headers=HEADERS,json={"session_id":sid,"message":"VPN 접수 요청"}).json()["proposal_id"]
        url="/api/proposals/"+proposal+"/approve"
        denied=client.post(url,headers={"Authorization":"Bearer "+"r"*32},json={"confirmed":True})
        assert denied.status_code==403
        assert client.get("/api/tickets",headers=HEADERS).json()==[]
        first=client.post(url,headers=HEADERS,json={"confirmed":True})
        second=client.post(url,headers=HEADERS,json={"confirmed":True})
        assert first.status_code==second.status_code==200 and first.json()==second.json()
        assert len(client.get("/api/tickets",headers=HEADERS).json())==1
    batches=[p["resourceSpans"][0]["scopeSpans"][0]["spans"] for p in payloads]
    approvals=[spans for spans in batches if spans[0]["name"]=="service-desk.approve"]
    assert len(approvals)==3
    assert all(s["status"]["code"]==2 for s in approvals[0])
    refs=[]
    for spans in approvals[1:]:
        assert len(spans)==2 and spans[1]["parentSpanId"]==spans[0]["spanId"]
        attrs={a["key"]:a["value"]["stringValue"] for a in spans[0]["attributes"]}
        refs.append(json.loads(attrs["langfuse.observation.output"])["ticket_ref"])
        assert proposal not in json.dumps(spans) and "VPN" not in json.dumps(spans,ensure_ascii=False)
    assert refs[0]==refs[1]


import pytest
from unittest.mock import Mock
from python_foundation.agent_memory import MemoryItem


@pytest.mark.parametrize("via_chat", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_memory_telemetry_excludes_body_query_ids_and_exception(tmp_path, via_chat, fail):
    payloads = []
    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={})
    telemetry = ChatTelemetry("http://localhost", "pk", "sk", capture_content=True,
                              transport=httpx.MockTransport(handle))
    memory = Mock()
    note = MemoryItem(id="sensitive-memory-id", text="sensitive-returned-memory")
    memory.save.return_value = note
    memory.search.return_value = [note]
    if fail:
        memory.save.side_effect = RuntimeError("sensitive-backend-exception")
        memory.search.side_effect = RuntimeError("sensitive-backend-exception")
    planner = Mock(side_effect=AssertionError("Explicit memory must bypass planner"))
    app = create_app(database_url="sqlite:///" + str(tmp_path / "memory.db"), accounts=ACCOUNTS,
                     memory_store=memory, planner=planner, telemetry=telemetry)
    with TestClient(app, raise_server_exceptions=False) as client:
        sid = client.post("/api/sessions", headers=HEADERS).json()["session_id"]
        for save in (True, False):
            if via_chat:
                url = "/api/chat"
                body = {"session_id": sid, "message": ("remember: " if save else "recall: ") + "sensitive-request"}
            else:
                url = "/api/memories" + ("" if save else "/search")
                body = {"text" if save else "query": "sensitive-request"}
            response = client.post(url, headers=HEADERS, json=body)
            assert response.status_code == (500 if fail else 200)
    planner.assert_not_called()
    assert memory.save.call_args.args[0].subject == "observer"
    assert memory.search.call_args.args[0].subject == "observer"
    assert len(payloads) == 2
    serialized = json.dumps(payloads)
    assert "sensitive-" not in serialized and "observer" not in serialized
    assert "langfuse.observation.input" not in serialized
    assert "langfuse.observation.output" not in serialized
    for index, payload in enumerate(payloads):
        root, child = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert child["name"] == ("tool.memory-save" if index == 0 else "tool.memory-search")
        assert child["parentSpanId"] == root["spanId"]
        assert int(root["startTimeUnixNano"]) <= int(child["startTimeUnixNano"]) <= int(child["endTimeUnixNano"]) <= int(root["endTimeUnixNano"])
        assert root["status"]["code"] == child["status"]["code"] == (2 if fail else 1)
        attrs = {a["key"]: a["value"]["stringValue"] for a in root["attributes"]}
        if not fail:
            assert attrs["langfuse.observation.metadata.memory_count"] == "1"
        else:
            assert "langfuse.observation.metadata.memory_count" not in attrs


def test_restricted_config_file_loads_without_environment_keys(tmp_path, monkeypatch):
    config = tmp_path / 'langfuse.json'
    config.write_text(json.dumps({'url': 'http://localhost', 'public_key': 'pk', 'secret_key': 'sk'}))
    config.chmod(0o640)
    for key in ('URL', 'PUBLIC_KEY', 'SECRET_KEY', 'CAPTURE_CONTENT'):
        monkeypatch.delenv('DESK_LANGFUSE_' + key, raising=False)
    monkeypatch.setenv('DESK_LANGFUSE_CONFIG', str(config))
    telemetry = ChatTelemetry.from_env()
    try:
        assert telemetry.url == 'http://localhost' and telemetry.capture_content is False
    finally:
        telemetry.close()


@pytest.mark.parametrize('problem', ['world_readable', 'group_writable', 'symlink', 'bad_boolean', 'conflict', 'extra_field'])
def test_unsafe_config_is_rejected_before_exporter_starts(tmp_path, monkeypatch, problem):
    config = tmp_path / 'langfuse.json'
    data = {'url': 'http://localhost', 'public_key': 'pk', 'secret_key': 'sk'}
    if problem == 'bad_boolean': data['capture_content'] = 'false'
    if problem == 'extra_field': data['password'] = 'not-allowed'
    config.write_text(json.dumps(data))
    config.chmod(0o644 if problem == 'world_readable' else 0o660 if problem == 'group_writable' else 0o600)
    for key in ('URL', 'PUBLIC_KEY', 'SECRET_KEY', 'CAPTURE_CONTENT'):
        monkeypatch.delenv('DESK_LANGFUSE_' + key, raising=False)
    if problem == 'symlink':
        link = tmp_path / 'linked.json'
        link.symlink_to(config)
        config = link
    monkeypatch.setenv('DESK_LANGFUSE_CONFIG', str(config))
    if problem == 'conflict': monkeypatch.setenv('DESK_LANGFUSE_URL', 'http://another-host')
    with pytest.raises((ValueError, OSError)):
        ChatTelemetry.from_env()
