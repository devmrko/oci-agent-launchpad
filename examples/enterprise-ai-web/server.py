"""Local-only, bounded OCI Enterprise AI teaching app."""
import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import sys


def preflight():
    """Local checks only: no model invocation and no resource creation."""
    from importlib.metadata import PackageNotFoundError, version
    failures = []
    if sys.version_info < (3, 12):
        failures.append("Python 3.12 이상으로 실행해 주세요.")
    for package in ("openai", "oci-genai-auth", "httpx"):
        try:
            print(f"{package}: {version(package)}")
        except PackageNotFoundError:
            failures.append(f"{package} 미설치: bash examples/enterprise-ai-web/setup.sh를 실행하세요.")
    try:
        import oci
        config = oci.config.from_file()
        oci.config.validate_config(config)
        if not Path(config.get("key_file", "")).expanduser().is_file():
            failures.append("OCI DEFAULT 프로필의 서명 키 파일을 찾지 못했습니다.")
    except Exception:
        failures.append("~/.oci/config DEFAULT 프로필과 OCI 서명 키 설정을 확인하세요.")
    for failure in failures:
        print(f"확인 필요: {failure}")
    if not failures:
        print("로컬 준비 점검 통과. OCI 권한·프로젝트 ACTIVE 상태·모델 지원은 실제 호출에서 확인합니다.")
    return not failures


def validate(value):
    if not isinstance(value, dict) or set(value) != {"nights", "use_tool"}:
        raise ValueError("숙박 일수와 계산 도구 여부만 입력해 주세요.")
    if type(value["nights"]) is not int or not 1 <= value["nights"] <= 10:
        raise ValueError("숙박 일수는 1~10 사이의 정수여야 합니다.")
    if type(value["use_tool"]) is not bool:
        raise ValueError("계산 도구 선택이 올바르지 않습니다.")
    return value


def assess(response, calls, expected, use_tool):
    """An API completion is separate from a verified calculation."""
    answer_complete = response.status == "completed" and bool(response.output_text.strip())
    executed = any(c.status == "completed" and c.outputs for c in calls)
    matched = any(
        c.status == "completed" and any(
            o.type == "logs" and o.logs.strip() == str(expected) for o in c.outputs or []
        ) for c in calls
    )
    if not answer_complete:
        status = "incomplete_answer"
    elif use_tool and not executed:
        status = "missing_tool_output"
    elif use_tool and not matched:
        status = "calculation_mismatch"
    else:
        status = "calculation_verified" if use_tool else "answer_received"
    return {"completed": answer_complete, "tool_verified": bool(executed),
            "calculation_verified": matched, "verification": status}


def invoke(project, region, value):
    import httpx
    from oci_genai_auth import OciUserPrincipalAuth
    from openai import OpenAI
    options = {}
    if value["use_tool"]:
        options = dict(
            tools=[{"type": "code_interpreter", "container": {"type": "auto", "memory_limit": "1g"}}],
            tool_choice="required", include=["code_interpreter_call.outputs"],
            instructions="Use the python tool. Print only the integer total without labels or separators. Then explain briefly in Korean.",
        )
    with OpenAI(
        base_url=f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1",
        api_key="not-used", project=project, timeout=45, max_retries=0,
        http_client=httpx.Client(auth=OciUserPrincipalAuth(
            config_file=str(Path.home() / ".oci/config"), profile_name="DEFAULT")),
    ) as client:
        response = client.responses.create(
            model="google.gemini-2.5-flash", store=False, max_output_tokens=1024,
            input=("가상 출장 규정: 국내 숙박비는 1박당 최대 100,000원입니다. "
                   f"식비와 교통비를 제외하고 {value['nights']}박의 숙박비 한도와 계산식을 한국어 한 문장으로만 답하세요. 제목이나 추가 설명은 쓰지 마세요."),
            **options,
        )
        calls = [item for item in response.output if item.type == "code_interpreter_call"]
        cleanup = []
        for container in {item.container_id for item in calls}:
            try:
                client.containers.delete(container)
                cleanup.append("임시 계산 환경 삭제 완료")
            except Exception:
                cleanup.append("임시 계산 환경 삭제 실패 — 서버 기록의 ID로 정리가 필요합니다")
                print("Container cleanup required:", container, flush=True)
        return {
            "answer": response.output_text,
            **assess(response, calls, value["nights"] * 100000, value["use_tool"]),
            "model": response.model, "region": region,
            "tokens": response.usage.total_tokens if response.usage else None,
            "expected": value["nights"] * 100000,
            "calls": [{"code": c.code, "outputs": [o.model_dump() for o in c.outputs or []]} for c in calls],
            "cleanup": cleanup,
        }


class Server(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, port, project, region, runner=None):
        super().__init__(("127.0.0.1", port), Handler)
        self.project, self.region = project, region
        self.token = secrets.token_urlsafe(32)
        self.gate = threading.Lock()
        self.remaining = 10
        self.runner = runner or invoke


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, data, mime="application/json; charset=utf-8"):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def correct_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.correct_host():
            return self.send(403, {"error": "로컬 주소로 접속해 주세요."})
        if self.path == "/":
            page = Path(__file__).with_name("index.html").read_text().replace("__TOKEN__", self.server.token)
            return self.send(200, page.encode(), "text/html; charset=utf-8")
        if self.path == "/health":
            return self.send(200, {"status": "up", "remaining": self.server.remaining})
        self.send(404, {"error": "없는 경로입니다."})

    def do_POST(self):
        self.connection.settimeout(10)
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        if (not self.correct_host() or self.headers.get("Origin") != expected_origin
                or not hmac.compare_digest(self.headers.get("X-Demo-Token", "").encode(), self.server.token.encode())):
            return self.send(403, {"error": "로컬 체험 화면에서 다시 시도해 주세요."})
        if self.path != "/api/run":
            return self.send(404, {"error": "없는 경로입니다."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024 or self.headers.get("Content-Type") != "application/json":
                raise ValueError("입력 형식이 올바르지 않습니다.")
            value = validate(json.loads(self.rfile.read(size)))
        except (ValueError, UnicodeError):
            return self.send(400, {"error": "숙박 1~10박과 계산 도구 선택을 확인해 주세요."})
        if not self.server.gate.acquire(blocking=False):
            return self.send(429, {"error": "앞선 요청이 끝난 후 다시 시도해 주세요."})
        try:
            if self.server.remaining <= 0:
                return self.send(429, {"error": "이번 실행의 체험 한도 10회를 사용했습니다."})
            self.server.remaining -= 1
            try:
                result = self.server.runner(self.server.project, self.server.region, value)
                result["remaining"] = self.server.remaining
                self.send(200, result)
            except Exception as error:
                print("OCI request failed:", type(error).__name__, flush=True)
                self.send(502, {"error": "OCI 호출이 완료되지 않았습니다. 프로젝트 상태·권한·모델 지원을 확인해 주세요."})
        finally:
            self.server.gate.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project")
    parser.add_argument("--region")
    parser.add_argument("--check", action="store_true", help="로컬 준비만 확인하며 OCI를 호출하지 않습니다")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    if args.check:
        raise SystemExit(0 if preflight() else 1)
    if not args.project or not args.region:
        parser.error("--project와 --region을 지정해 주세요. 처음이면 --check로 준비 상태를 확인하세요.")
    if not preflight():
        raise SystemExit(1)
    with Server(args.port, args.project, args.region) as server:
        print(f"Local demo: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
