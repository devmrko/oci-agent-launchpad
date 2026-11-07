"""Optional, bounded, best-effort export of completed chat requests to Langfuse."""
import json
from contextlib import contextmanager
import logging
import os
import queue
import stat
import secrets
import threading
import time
from urllib.parse import urlparse
import httpx

log = logging.getLogger(__name__)

@contextmanager
def capture_stage(stages, name, kind):
    stage = {"name": name, "kind": kind, "start": time.time_ns()}
    try:
        yield stage
    except Exception as failure:
        stage["error"] = getattr(getattr(failure, "error", None), "code", type(failure).__name__)
        raise
    finally:
        stage["end"] = time.time_ns()
        if stages is not None:
            stages.append(stage)


class ChatTelemetry:
    def __init__(self, url, public_key, secret_key, *, capture_content=False, transport=None):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Invalid Langfuse URL")
        if not public_key or not secret_key:
            raise ValueError("Langfuse keys required")
        self.url, self.auth = url.rstrip("/"), (public_key, secret_key)
        self.capture_content, self.transport = capture_content, transport
        self.pending = queue.Queue(maxsize=100)
        self.stop = threading.Event()
        self.sent = self.dropped = self.failed = 0
        self.worker = threading.Thread(target=self._run, daemon=True, name="desk-telemetry")
        self.worker.start()

    @classmethod
    def from_env(cls):
        config_path = os.environ.get("DESK_LANGFUSE_CONFIG")
        if config_path:
            if any(os.environ.get(key) is not None for key in (
                "DESK_LANGFUSE_URL", "DESK_LANGFUSE_PUBLIC_KEY", "DESK_LANGFUSE_SECRET_KEY",
                "DESK_LANGFUSE_CAPTURE_CONTENT",
            )):
                raise ValueError("Use either Langfuse config file or environment settings")
            # Open once without following symlinks; reject shared writable/readable files.
            fd = os.open(config_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd) as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o027 or info.st_size > 16384:
                    raise ValueError("Langfuse config requires a restricted regular file")
                config = json.load(stream)
            required = {"url", "public_key", "secret_key"}
            if not isinstance(config, dict) or not required <= config.keys() or config.keys() - required - {"capture_content"}:
                raise ValueError("Invalid Langfuse config fields")
            if any(not isinstance(config[key], str) or not config[key] for key in required):
                raise ValueError("Invalid Langfuse config value")
            capture = config.get("capture_content", False)
            if type(capture) is not bool:
                raise ValueError("Langfuse capture_content must be boolean")
            return cls(config["url"], config["public_key"], config["secret_key"], capture_content=capture)
        url = os.environ.get("DESK_LANGFUSE_URL")
        if not url:
            return None
        return cls(url, os.environ["DESK_LANGFUSE_PUBLIC_KEY"], os.environ["DESK_LANGFUSE_SECRET_KEY"],
                   capture_content=os.environ.get("DESK_LANGFUSE_CAPTURE_CONTENT") == "true")

    def record(self, message, result, started, stages=(), error=None, operation="chat", input_data=None, output_data=None, suppress_content=False):
        trace = result.get("trace", {})
        attrs = {"langfuse.observation.type": "agent", "langfuse.trace.name": "service-desk." + operation,
                 "langfuse.observation.metadata.mode": trace.get("mode", "unknown"),
                 "langfuse.observation.metadata.request_id": trace.get("request_id", ""),
                 "langfuse.observation.metadata.model": json.dumps(trace.get("model", {})),
                 "langfuse.observation.metadata.synthetic_business_data": "true"}
        memory_request = suppress_content or trace.get("mode") == "explicit-memory" or operation in {"memory-save", "memory-search"}
        memory = trace.get("memory", {})
        if memory_request:
            attrs["langfuse.observation.metadata.content_policy"] = "memory-body-excluded"
            if "count" in memory:
                attrs["langfuse.observation.metadata.memory_count"] = str(memory["count"])
            attrs["langfuse.observation.metadata.memory_backend"] = "oracle-agent-memory"
        if self.capture_content and error is None and not memory_request:
            # Explicit content opt-in: never export the entire request/headers, memory results or account identity.
            attrs["langfuse.observation.input"] = json.dumps(input_data if input_data is not None else {"message": message[:2000]}, ensure_ascii=False)
            attrs["langfuse.observation.output"] = json.dumps(output_data if output_data is not None else {"answer": str(result.get("answer", ""))[:8000]}, ensure_ascii=False)
        span = {"traceId": secrets.token_hex(16), "spanId": secrets.token_hex(8), "name": "service-desk." + operation, "kind": 1,
                "startTimeUnixNano": str(started), "endTimeUnixNano": str(time.time_ns()),
                "attributes": [{"key": k, "value": {"stringValue": str(v)}} for k,v in attrs.items()], "status": {"code": 1}}
        if error:
            span["status"] = {"code": 2}
            span["attributes"].extend([
                {"key": "langfuse.observation.level", "value": {"stringValue": "ERROR"}},
                {"key": "langfuse.observation.status_message", "value": {"stringValue": error}},
            ])
        spans = [span]
        for stage in stages:
            child_attrs = {"langfuse.observation.type": stage["kind"], "langfuse.trace.name": "service-desk." + operation,
                           "langfuse.observation.metadata.request_id": trace.get("request_id", "")}
            if self.capture_content and not stage.get("error") and not memory_request:
                for field in ("input", "output"):
                    if field in stage:
                        child_attrs["langfuse.observation." + field] = json.dumps(stage[field], ensure_ascii=False)
            if "memory_count" in stage:
                child_attrs["langfuse.observation.metadata.memory_count"] = str(stage["memory_count"])
            if stage.get("model"):
                child_attrs["langfuse.observation.metadata.model"] = json.dumps(stage["model"])
            if stage.get("error"):
                child_attrs["langfuse.observation.level"] = "ERROR"
                child_attrs["langfuse.observation.status_message"] = stage["error"]
            spans.append({"traceId": span["traceId"], "parentSpanId": span["spanId"], "spanId": secrets.token_hex(8),
                          "name": stage["name"], "kind": 1, "startTimeUnixNano": str(stage["start"]), "endTimeUnixNano": str(stage["end"]),
                          "attributes": [{"key": k, "value": {"stringValue": str(v)}} for k,v in child_attrs.items()],
                          "status": {"code": 2 if stage.get("error") else 1}})
        payload = {"resourceSpans": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "launchpad-service-desk"}}]},
                    "scopeSpans": [{"scope": {"name": "service-desk-chat"}, "spans": spans}]}]}
        try:
            self.pending.put_nowait(payload)
        except queue.Full:
            self.dropped += 1
            log.warning("telemetry_queue_full dropped=%d", self.dropped)

    def _run(self):
        with httpx.Client(timeout=2, follow_redirects=False, trust_env=False, transport=self.transport) as client:
            while not self.stop.is_set() or not self.pending.empty():
                try:
                    payload = self.pending.get(timeout=.1)
                except queue.Empty:
                    continue
                try:
                    response = client.post(self.url + "/api/public/otel/v1/traces", auth=self.auth,
                                           headers={"x-langfuse-ingestion-version": "4"}, json=payload)
                    response.raise_for_status()
                    if response.json().get("partialSuccess", {}).get("rejectedSpans"):
                        raise ValueError("Rejected spans")
                    self.sent += 1
                except Exception:
                    self.failed += 1
                    log.warning("telemetry_export_failed failed=%d", self.failed)
                finally:
                    self.pending.task_done()

    def close(self):
        self.stop.set()
        self.worker.join(timeout=3)
        if self.worker.is_alive():
            log.warning("telemetry_shutdown_incomplete pending=%d", self.pending.qsize())
