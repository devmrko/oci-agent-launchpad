import json
import os
import secrets
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from python_foundation.agent_memory import MemoryInput, MemoryQuery
from python_foundation.database import create_database, sessions
from python_foundation.errors import AuthenticationRequired, BusinessError, ErrorCategory, ErrorSpec
from python_foundation.security import Actor, Security, current_actor
from python_foundation.settings import FoundationSettings
from python_foundation.web import install_web

from .models import Base
from .planning import OciPlanner
from .service import DeskService


class DemoVerifier:
    def __init__(self, accounts):
        if not accounts or any(len(k) < 24 for k in accounts):
            raise ValueError("DESK_DEMO_ACCOUNTS must contain tokens of at least 24 characters")
        self.accounts = accounts

    def verify(self, token):
        for known, account in self.accounts.items():
            if secrets.compare_digest(token, known):
                scopes = {"SCOPE_requests:write"} if account.get("can_write") else set()
                return Actor("desk-demo", account["subject"], frozenset(scopes))
        raise AuthenticationRequired()


class Chat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class Language(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["ko", "en"]


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]


def model_planner(message):
    endpoint = os.environ["DESK_MODEL_URL"]
    if not endpoint.startswith("https://"):
        raise ValueError("Model endpoint must use HTTPS")
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                endpoint,
                headers={"Authorization": "Bearer " + os.environ["DESK_MODEL_KEY"]},
                json={
                    "model": os.environ["DESK_MODEL_NAME"],
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "system",
                            "content": 'Select action only. Return JSON {"action":"search"} or {"action":"propose"}. Propose only when the user asks to submit a support request. Never execute actions.',
                        },
                        {"role": "user", "content": message},
                    ],
                },
            )
            response.raise_for_status()
            return json.loads(response.json()["choices"][0]["message"]["content"])["action"]
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as failure:
        raise BusinessError(
            ErrorSpec("MODEL_UNAVAILABLE", ErrorCategory.UNAVAILABLE, "모델 연결을 확인해 주세요.")
        ) from failure


def create_app(*, database_url=None, accounts=None, planner=None, memory_store=None):
    mode = os.environ.get("DESK_AUTH_MODE", "demo")
    if accounts is not None or mode == "demo":
        settings = FoundationSettings(
            auth_mode="token",
            issuer="https://demo.invalid",
            audience="desk",
            jwks_url="https://demo.invalid/jwks",
            database_url=SecretStr(database_url or os.environ.get("DESK_DATABASE_URL", "sqlite:///desk.db")),
        )
        verifier = DemoVerifier(
            accounts if accounts is not None else json.loads(os.environ.get("DESK_DEMO_ACCOUNTS", "{}"))
        )
    elif mode == "jwt":
        settings = FoundationSettings(
            auth_mode="token",
            environment="production",
            database_url=SecretStr(database_url or os.environ["DESK_DATABASE_URL"]),
        )
        verifier = None
    else:
        raise ValueError("DESK_AUTH_MODE must be demo or jwt")
    engine = create_database(settings)
    Base.metadata.create_all(engine)
    backend = os.environ.get("DESK_MODEL_BACKEND", "http" if os.environ.get("DESK_MODEL_URL") else "demo")
    if planner is None and backend == "oci":
        planner = OciPlanner(
            region=os.environ["DESK_OCI_REGION"],
            compartment=os.environ["DESK_OCI_COMPARTMENT"],
            model=os.environ.get("DESK_MODEL_NAME", "google.gemini-2.5-flash-lite"),
            auth=os.environ.get("DESK_OCI_AUTH", "instance"),
        )
    elif backend not in {"demo", "http", "oci"}:
        raise ValueError("Unsupported DESK_MODEL_BACKEND")
    memory_pool = memory_client = None
    if memory_store is None and os.environ.get("DESK_MEMORY_CONFIG"):
        from .memory_backend import resources

        memory_store, memory_pool, memory_client = resources()
    service = DeskService(
        sessions(engine), planner=planner or (model_planner if os.environ.get("DESK_MODEL_URL") else None)
    )

    service.memory_store = memory_store

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()
        if memory_client is not None:
            memory_client.close()
        if memory_pool is not None:
            memory_pool.close()

    app = FastAPI(title="Service Desk — synthetic example", version="0.3.0", lifespan=lifespan)
    install_web(app, Security(settings, verifier=verifier))
    app.state.desk = service
    actor_type = Annotated[Actor, Depends(current_actor)]

    @app.get("/health")
    def health():
        from sqlalchemy import text

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "UP", "version": "0.3.0", "synthetic": True}

    @app.post("/api/sessions")
    def new_session(actor: actor_type):
        return service.new_session(actor)

    @app.post("/api/chat")
    def chat(body: Chat, actor: actor_type, request: Request):
        return service.chat(actor, body.session_id, body.message, request.state.request_id)

    @app.post("/api/proposals/{proposal_id}/approve")
    def approve(proposal_id: str, body: Approval, actor: actor_type, request: Request):
        return service.approve(actor, proposal_id, request.state.request_id)

    @app.get("/api/tools")
    def tool_catalog(actor: actor_type):
        return service.gateway("catalog", "none").catalog()

    @app.get("/api/tickets")
    def tickets(actor: actor_type):
        return service.listing(actor, "ticket")

    @app.get("/api/traces")
    def traces(actor: actor_type):
        return service.listing(actor, "trace")

    @app.post("/api/memories")
    def save_durable_memory(body: MemoryInput, actor: actor_type, request: Request):
        return service.durable_memory(actor, body, request.state.request_id, save=True)

    @app.post("/api/memories/search")
    def search_durable_memory(body: MemoryQuery, actor: actor_type, request: Request):
        return service.durable_memory(actor, body, request.state.request_id)

    @app.get("/api/memory")
    def memory(actor: actor_type):
        return service.preference(actor)

    @app.put("/api/memory")
    def put_memory(body: Language, actor: actor_type):
        return service.preference(actor, body.language)

    @app.delete("/api/memory")
    def delete_memory(actor: actor_type):
        return service.preference(actor, delete=True)

    return app
