"""Start a loopback-only demo with generated credentials stored outside Git."""

import json
import os
import secrets
from pathlib import Path

import uvicorn

state = Path(".run")
state.mkdir(mode=0o700, exist_ok=True)
credentials = state / "demo-accounts.json"
if not credentials.exists():
    accounts = {secrets.token_urlsafe(32): {"subject": "demo-user", "can_write": True}}
    fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(accounts, stream)
os.environ["DESK_AUTH_MODE"] = "demo"
os.environ["DESK_DEMO_ACCOUNTS"] = credentials.read_text()
os.environ.setdefault("DESK_DATABASE_URL", "sqlite:///.run/desk.db")
print("Local demo: http://127.0.0.1:8092/docs ; credentials: .run/demo-accounts.json")
uvicorn.run("service_desk.app:create_app", factory=True, host="127.0.0.1", port=8092)
