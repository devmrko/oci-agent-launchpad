"""Independent Hello Agent API and small browser playground."""
import json
import os
import secrets
import time
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from python_foundation.security import Actor, Security, current_actor
from python_foundation.settings import FoundationSettings
from python_foundation.errors import AuthenticationRequired
from python_foundation.web import install_web
from agent import validate, execute, oci_decision
from hello_telemetry import export
from hello_release import load as load_release

VERSION = "0.1.0"
PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Hello Agent · OCI</title><style>body{font:17px system-ui;max-width:760px;margin:50px auto;padding:20px;background:#f6f8fa;color:#18212d}input,button{font:inherit;padding:12px;margin:6px 0;box-sizing:border-box}input{width:100%}button{background:#174e5c;color:white;border:0;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px}label{display:block}small{color:#475569}</style>
<h1>Hello Agent</h1><p>OCI 모델이 도구를 선택하고, 배포된 앱이 현재 시간을 조회합니다.</p>
<p><small>합성 데모 전용: 입력·출력이 Langfuse에 기록됩니다. 개인정보를 입력하지 마세요.</small></p>
<label>접근 토큰<input id="token" type="password" autocomplete="off"></label>
<label>질문<input id="message" maxlength="1000" value="지금 서울 몇 시인가요?"></label>
<button id="send">에이전트 실행</button><p id="status" role="status"></p><pre id="output">실행 결과와 trace ID가 여기에 표시됩니다.</pre>
<script>document.getElementById('send').onclick=async()=>{const b=document.getElementById('send');b.disabled=true;document.getElementById('status').textContent='OCI 모델과 도구 실행 중…';try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+document.getElementById('token').value},body:JSON.stringify({message:document.getElementById('message').value})});const d=await r.json();document.getElementById('status').textContent=r.ok?'실행 완료':'실행 실패';document.getElementById('output').textContent=JSON.stringify(d,null,2);}catch(e){document.getElementById('status').textContent='연결 실패';}finally{b.disabled=false;}};</script></html>"""

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)

class Verifier:
    def __init__(self, token):
        if len(token) < 32: raise ValueError("HELLO_TOKEN must contain at least 32 characters")
        self.token = token
    def verify(self, token):
        if not secrets.compare_digest(token, self.token): raise AuthenticationRequired()
        return Actor("hello-demo", "demo-user", frozenset())


def create_app(*, planner=None, token=None, telemetry=None):
    settings = FoundationSettings(auth_mode="token", issuer="https://demo.invalid", audience="hello", jwks_url="https://demo.invalid/jwks")
    app = FastAPI(title="Hello Agent", version=VERSION)
    install_web(app, Security(settings, verifier=Verifier(token or os.environ["HELLO_TOKEN"])))
    model = planner or oci_decision
    release = load_release(os.environ.get("HELLO_RELEASE_IDENTITY"))
    cfg = telemetry
    if cfg is None and os.environ.get("HELLO_LANGFUSE_CONFIG"):
        cfg = json.loads(Path(os.environ["HELLO_LANGFUSE_CONFIG"]).read_text())
    @app.get("/", response_class=HTMLResponse)
    def home(): return PAGE
    @app.get("/health")
    def health(): return {"status": "UP", "version": VERSION, "agent_id": "hello-agent", "release": release}
    @app.get("/api/capabilities", dependencies=[Depends(current_actor)])
    def capabilities():
        return {"schema_version": 1, "app_version": VERSION, "agent_id": "hello-agent", "capabilities": {
            k: {"status": ("configured" if k == "runtime" or (k == "observability" and cfg) else "partial" if k in {"identity", "policy"} else "not_configured" if k == "observability" else "not_implemented")}
            for k in ["runtime", "memory", "identity", "gateway", "policy", "observability", "evaluations", "code_interpreter", "browser"]}}
    @app.get("/api/traces", dependencies=[Depends(current_actor)])
    def legacy_traces():
        # No local execution database; authoritative details live in Langfuse.
        return []
    @app.post("/api/chat", dependencies=[Depends(current_actor)])
    def chat(body: Input):
        if not body.message.strip(): raise HTTPException(422, "Empty message")
        trace_id = secrets.token_hex(16)
        start = time.time_ns()
        try:
            raw = model(body.message)
            decision = validate(raw)
            chosen = time.time_ns()
            data = execute(decision)
            ended = time.time_ns()
        except Exception:
            raise HTTPException(502, "OCI model or tool execution failed") from None
        answer = (f"{data['city']}의 현재 시간은 {data['time']}입니다." if decision["tool"] == "get_time" else data["message"])
        result = {"answer": answer, "decision": decision, "tool_result": data,
                  "trace_id": trace_id, "version": VERSION, "mode": "oci", "release": release}
        stages = [("oci.model", "generation", start, chosen, body.message, raw),
                  (decision["tool"], "tool", chosen, ended, decision["arguments"], data)]
        result["telemetry"] = export(cfg["url"], cfg["public_key"], cfg["secret_key"], trace_id,
                                     body.message, result, stages) if cfg else "disabled"
        return result
    return app
