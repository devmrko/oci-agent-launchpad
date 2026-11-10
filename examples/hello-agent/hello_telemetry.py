"""Bounded OTLP export; no durable logging or hidden retry."""
import json
import logging
import secrets
import time
import httpx


def export(url, public, secret, trace_id, message, result, stages):
    parent = secrets.token_hex(8)
    def span(name, kind, start, end, inp, out, parent_id=None):
        attrs = {"langfuse.observation.type": kind, "langfuse.trace.name": "hello-agent.chat",
                 "langfuse.observation.input": json.dumps(inp, ensure_ascii=False),
                 "langfuse.observation.output": json.dumps(out, ensure_ascii=False),
                 "langfuse.observation.metadata.agent_id": "hello-agent"}
        for key, value in (result.get("release") or {}).items():
            attrs["langfuse.observation.metadata." + key] = value
        item = {"traceId": trace_id, "spanId": secrets.token_hex(8) if parent_id else parent,
                "name": name, "kind": 1, "startTimeUnixNano": str(start), "endTimeUnixNano": str(end),
                "attributes": [{"key": k, "value": {"stringValue": v}} for k,v in attrs.items()],
                "status": {"code": 1}}
        if parent_id: item["parentSpanId"] = parent_id
        return item
    spans = [span("hello-agent.chat", "agent", stages[0][2], time.time_ns(), message, result)]
    spans += [span(name, kind, start, end, inp, out, parent) for name,kind,start,end,inp,out in stages]
    payload = {"resourceSpans": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "hello-agent"}}]},
                 "scopeSpans": [{"scope": {"name": "hello-agent"}, "spans": spans}]}]}
    try:
        with httpx.Client(timeout=2, follow_redirects=False, trust_env=False) as client:
            response = client.post(url.rstrip("/") + "/api/public/otel/v1/traces", auth=(public, secret),
                headers={"x-langfuse-ingestion-version": "4"}, json=payload)
            response.raise_for_status()
            if response.json().get("partialSuccess", {}).get("rejectedSpans"):
                raise ValueError("Rejected spans")
        return "exported"
    except Exception:
        logging.getLogger(__name__).warning("telemetry_export_failed trace_id=%s", trace_id)
        return "failed"
