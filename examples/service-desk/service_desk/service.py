import hashlib
import json
import time
import uuid
from dataclasses import asdict

from pydantic import BaseModel, ConfigDict, Field
from python_foundation.agent_memory import MemoryInput, MemoryQuery
from python_foundation.agents import ExecutionContext, ToolDefinition, ToolGateway
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import BusinessError, ErrorCategory, ErrorSpec
from sqlalchemy.exc import IntegrityError

from . import __version__
from .models import Record
from .planning import Decision
from .observability import capture_stage
from .repository import DeskRepository

DOCS = [
    {
        "id": "POL-VPN-01",
        "keywords": ["vpn", "접속"],
        "en": "[Synthetic policy] VPN requires MFA enrollment. Report connection failures to IT support.",
        "text": "[합성 규정] VPN은 MFA 등록 후 사용합니다. 접속 장애는 IT 지원 요청으로 접수합니다.",
    },
    {
        "id": "POL-LAPTOP-01",
        "keywords": ["노트북", "장비", "laptop"],
        "en": "[Synthetic policy] Laptop replacement requires manager approval before contacting IT support.",
        "text": "[합성 규정] 노트북 교체는 팀장 승인 후 IT 지원팀에 요청합니다.",
    },
]


class ChatToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class ApprovalToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: str = Field(min_length=1, max_length=100)


class ToolOutput(BaseModel):
    data: dict


class DeskService:
    def __init__(self, factory, planner=None):
        self.factory = factory
        self.planner = planner
        self.memory_store = None

    @staticmethod
    def owner(actor):
        return hashlib.sha256(json.dumps([actor.issuer, actor.subject]).encode()).hexdigest()

    def new_session(self, actor):
        key = str(uuid.uuid4())
        with SqlAlchemyUnitOfWork(self.factory) as u:
            DeskRepository(u.session).add(key, self.owner(actor), "session", {"turns": 0})
        return {"session_id": key}

    def _authorize_chat(self, actor, body):
        with SqlAlchemyUnitOfWork(self.factory) as u:
            DeskRepository(u.session).get(body.session_id, self.owner(actor), "session")

    def _authorize_approval(self, actor, body):
        with SqlAlchemyUnitOfWork(self.factory) as u:
            DeskRepository(u.session).get(body.proposal_id, self.owner(actor), "proposal")

    def gateway(self, correlation, mode):
        return ToolGateway(
            [
                ToolDefinition(
                    "search",
                    "Search approved synthetic policies",
                    ChatToolInput,
                    self._authorize_chat,
                    lambda a, b: ToolOutput(data=self._chat_action(a, b, "search", correlation, mode)),
                ),
                ToolDefinition(
                    "propose",
                    "Create a draft support request; does not submit it",
                    ChatToolInput,
                    self._authorize_chat,
                    lambda a, b: ToolOutput(data=self._chat_action(a, b, "propose", correlation, mode)),
                ),
                ToolDefinition(
                    "memory-save",
                    "Save an explicit memory request",
                    ChatToolInput,
                    self._authorize_chat,
                    lambda a, b: ToolOutput(data=self._memory_chat(a, b, correlation, save=True)),
                ),
                ToolDefinition(
                    "memory-search",
                    "Recall user memories as untrusted references",
                    ChatToolInput,
                    self._authorize_chat,
                    lambda a, b: ToolOutput(data=self._memory_chat(a, b, correlation)),
                ),
                ToolDefinition(
                    "approve",
                    "Submit an existing user-approved draft",
                    ApprovalToolInput,
                    self._authorize_approval,
                    lambda a, b: ToolOutput(data=self._approve(a, b.proposal_id)),
                    required_authority="SCOPE_requests:write",
                ),
            ]
        )

    def chat(self, actor, session_id, message, correlation, stages=None):
        start = time.perf_counter()
        context = ExecutionContext(correlation, max_calls=1, timeout_seconds=30)
        metadata = {}
        try:
            # Ownership is checked before a prompt can be sent to the provider.
            body = ChatToolInput(session_id=session_id, message=message)
            self._authorize_chat(actor, body)
            mode = "live-model" if self.planner else "deterministic-demo"
            explicit = self.memory_command(message)
            if explicit:
                action = explicit[0]
            else:
                with capture_stage(stages, "model.route" if self.planner else "demo.route",
                                   "generation" if self.planner else "span") as stage:
                    stage["input"] = {"message": message[:2000]}
                    selected = self.planner(message) if self.planner else (
                        "propose" if any(w in message.lower() for w in ("요청", "등록", "접수")) else "search"
                    )
                    if isinstance(selected, Decision):
                        action, metadata = selected.action, selected.metadata
                    else:
                        action = selected
                    stage["output"] = {"selected_action": action if isinstance(action, str) else "invalid"}
                    stage["model"] = metadata
            allowed = {explicit[0]} if explicit else {"search", "propose"}
            if not isinstance(action, str) or action not in allowed:
                raise BusinessError(
                    ErrorSpec("INVALID_PLAN", ErrorCategory.VALIDATION, "허용되지 않은 도구입니다.")
                )
            with capture_stage(stages, "tool." + action, "tool") as stage:
                # Memory contents are not included in child tool observations.
                if action in {"search", "propose"}:
                    stage["input"] = {"message": message[:2000]}
                result = self.gateway(correlation, mode).invoke(context, actor, action, body.model_dump()).data
                if explicit:
                    stage["memory_count"] = result["trace"]["memory"]["count"]
                if action in {"search", "propose"}:
                    stage["output"] = {"answer": str(result.get("answer", ""))[:8000], "sources": result.get("sources", [])}

            result["trace"].update(
                model=metadata,
                tools=[asdict(e) for e in context.events],
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            with SqlAlchemyUnitOfWork(self.factory) as u:
                DeskRepository(u.session).add(str(uuid.uuid4()), self.owner(actor), "trace", result["trace"])
            return result
        except Exception as failure:
            code = failure.error.code if isinstance(failure, BusinessError) else type(failure).__name__
            self.audit(
                actor,
                correlation,
                "chat",
                "error",
                code,
                start,
                extra={"model": metadata, "session_id": session_id, "tools": [asdict(e) for e in context.events]},
            )
            raise

    def approve(self, actor, proposal_id, correlation=None):
        correlation = correlation or str(uuid.uuid4())
        context = ExecutionContext(correlation, max_calls=1)
        start = time.perf_counter()
        try:
            result = (
                self.gateway(correlation, "user-approval")
                .invoke(context, actor, "approve", {"proposal_id": proposal_id})
                .data
            )
        except Exception as failure:
            code = failure.error.code if isinstance(failure, BusinessError) else type(failure).__name__
            self.audit(
                actor,
                correlation,
                "approve",
                "error",
                code,
                start,
                extra={"tools": [asdict(e) for e in context.events]},
            )
            raise
        self.audit(
            actor,
            correlation,
            "approve",
            "ok",
            None,
            start,
            extra={"tools": [asdict(e) for e in context.events]},
        )
        return result

    def _chat_action(self, actor, body, action, correlation, mode):
        start = time.perf_counter()
        session_id, message = body.session_id, body.message
        owner = self.owner(actor)
        lowered = message.lower()
        hits = [d for d in DOCS if any(k in lowered for k in d["keywords"])]
        language = self.preference(actor)["language"] or "ko"
        answer = "\n".join(d["en" if language == "en" else "text"] for d in hits) or (
            "No supporting policy was found."
            if language == "en"
            else "등록된 규정에서 근거를 찾지 못했습니다."
        )
        proposal = None
        with SqlAlchemyUnitOfWork(self.factory) as u:
            repo = DeskRepository(u.session)
            session = repo.get(session_id, owner, "session")
            session.data = {"turns": session.data["turns"] + 1}
            if action == "propose":
                proposal = str(uuid.uuid4())
                repo.add(proposal, owner, "proposal", {"summary": message, "session_id": session_id})
                answer += (
                    "\nReview and approve the draft support request."
                    if language == "en"
                    else "\n지원 요청 초안을 만들었습니다. 내용을 확인한 뒤 승인해 주세요."
                )
            trace = {
                "request_id": correlation,
                "session_id": session_id,
                "mode": mode,
                "steps": [
                    "session-owner-check",
                    "model-plan" if self.planner else "demo-route",
                    "policy-allow",
                    action,
                ],
                "status": "ok",
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
                "app_version": __version__,
            }
        return {
            "answer": answer,
            "language": language,
            "sources": [d["id"] for d in hits],
            "proposal_id": proposal,
            "proposal_summary": message if proposal else None,
            "trace": trace,
        }

    def _approve(self, actor, proposal_id):
        actor.require("SCOPE_requests:write")
        owner = self.owner(actor)
        key = "ticket:" + proposal_id
        try:
            with SqlAlchemyUnitOfWork(self.factory) as u:
                repo = DeskRepository(u.session)
                proposal = repo.get(proposal_id, owner, "proposal")
                existing = u.session.get(Record, key)
                if existing:
                    return {"ticket_id": key, **existing.data}
                data = {"summary": proposal.data["summary"], "status": "registered", "synthetic": True}
                repo.add(key, owner, "ticket", data)
                return {"ticket_id": key, **data}
        except IntegrityError:
            with SqlAlchemyUnitOfWork(self.factory) as u:
                row = DeskRepository(u.session).get(key, owner, "ticket")
                return {"ticket_id": key, **row.data}

    def listing(self, actor, kind):
        with SqlAlchemyUnitOfWork(self.factory) as u:
            return [{"id": r.id, **r.data} for r in DeskRepository(u.session).list(self.owner(actor), kind)]

    def preference(self, actor, value=None, delete=False):
        owner = self.owner(actor)
        key = "language:" + owner
        with SqlAlchemyUnitOfWork(self.factory) as u:
            row = u.session.get(Record, key)
            if delete:
                if row:
                    u.session.delete(row)
                return {"language": None}
            if value is not None:
                if row:
                    row.data = {"language": value}
                else:
                    row = DeskRepository(u.session).add(key, owner, "preference", {"language": value})
            return row.data if row else {"language": None}

    def audit(self, actor, correlation, operation, status, error_code, start, extra=None):
        with SqlAlchemyUnitOfWork(self.factory) as u:
            DeskRepository(u.session).add(
                str(uuid.uuid4()),
                self.owner(actor),
                "trace",
                {
                    "request_id": correlation,
                    **(extra or {}),
                    "operation": operation,
                    "status": status,
                    "error_code": error_code,
                    "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
                    "app_version": __version__,
                },
            )

    def durable_memory(self, actor, command, correlation, save=False):
        start = time.perf_counter()
        operation = "memory-save" if save else "memory-search"
        try:
            if self.memory_store is None:
                raise BusinessError(
                    ErrorSpec(
                        "MEMORY_NOT_CONFIGURED",
                        ErrorCategory.UNAVAILABLE,
                        "장기 기억 저장소가 설정되지 않았습니다.",
                    )
                )
            result = (
                self.memory_store.save(actor, command) if save else self.memory_store.search(actor, command)
            )
        except Exception as failure:
            code = failure.error.code if isinstance(failure, BusinessError) else "MEMORY_FAILED"
            self.audit(
                actor,
                correlation,
                operation,
                "error",
                code,
                start,
                extra={"tools": [{"tool": operation, "stage": "execute", "status": "error"}]},
            )
            raise
        count = 1 if save else len(result)
        self.audit(
            actor,
            correlation,
            operation,
            "ok",
            None,
            start,
            extra={
                "memory": {"backend": "oracle-agent-memory", "count": count},
                "tools": [{"tool": operation, "stage": "execute", "status": "ok"}],
            },
        )
        return {"backend": "oracle-agent-memory", "items": [result] if save else result}

    @staticmethod
    def memory_command(message):
        for prefix, action in [
            ("기억해 주세요:", "memory-save"),
            ("기억해:", "memory-save"),
            ("remember:", "memory-save"),
            ("기억에서 찾아 주세요:", "memory-search"),
            ("recall:", "memory-search"),
        ]:
            if message.strip().lower().startswith(prefix):
                return action, message.strip()[len(prefix) :].strip()
        return None

    def _memory_chat(self, actor, body, correlation, save=False):
        command = self.memory_command(body.message)
        expected = "memory-save" if save else "memory-search"
        if command is None or command[0] != expected or not command[1]:
            raise BusinessError(
                ErrorSpec(
                    "INVALID_MEMORY_REQUEST",
                    ErrorCategory.VALIDATION,
                    "기억할 내용 또는 검색할 질문을 입력해 주세요.",
                )
            )
        if self.memory_store is None:
            raise BusinessError(
                ErrorSpec(
                    "MEMORY_NOT_CONFIGURED",
                    ErrorCategory.UNAVAILABLE,
                    "장기 기억 저장소가 설정되지 않았습니다.",
                )
            )
        if save:
            items = [self.memory_store.save(actor, MemoryInput(text=command[1]))]
            answer = "요청하신 내용을 기억에 저장했습니다."
        else:
            items = self.memory_store.search(actor, MemoryQuery(query=command[1][:500]))
            answer = (
                (
                    "저장된 사용자 기억입니다. 업무 규정이나 실행 지시가 아닙니다.\n"
                    + "\n".join(f"[{item.id}] {item.text}" for item in items)
                )
                if items
                else "관련된 기억을 찾지 못했습니다."
            )
        return {
            "answer": answer,
            "sources": ["memory:" + x.id for x in items],
            "memories": [x.model_dump() for x in items],
            "proposal_id": None,
            "trace": {
                "request_id": correlation,
                "session_id": body.session_id,
                "mode": "explicit-memory",
                "status": "ok",
                "app_version": __version__,
                "memory": {"backend": "oracle-agent-memory", "count": len(items)},
            },
        }
