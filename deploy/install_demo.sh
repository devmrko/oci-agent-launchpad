#!/usr/bin/env bash
# Run as root on the new Oracle Linux demo VM, after cloud-init completes.
set -euo pipefail
archive="${1:?source archive required}"
release=/opt/launchpad/releases/8c9efdd
install -d "$release"
tar -xzf "$archive" -C "$release"
python3.12 -m venv "$release/venv"
app="$release/launchpad/examples/service-desk"
"$release/venv/bin/python" -m pip install "$release/foundation" -r "$app/requirements.lock"
"$release/venv/bin/python" -m pip install --no-deps "$app"
id launchpad >/dev/null 2>&1 || useradd --system --home /var/lib/launchpad --shell /usr/sbin/nologin launchpad
install -d -o launchpad -g launchpad -m 700 /var/lib/launchpad
python3.12 - <<'BOOTSTRAP'
import json, os, secrets
from pathlib import Path
folder=Path('/var/lib/launchpad/.run')
folder.mkdir(mode=0o700, exist_ok=True)
accounts=folder/'demo-accounts.json'
if not accounts.exists():
    fd=os.open(accounts, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({secrets.token_urlsafe(32): {'subject':'demo-user','can_write':True}},stream)
config=Path('/etc/launchpad-demo.env')
fd=os.open(config, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
with os.fdopen(fd,'w') as stream:
    stream.write("DESK_AUTH_MODE=demo\nDESK_DATABASE_URL=sqlite:////var/lib/launchpad/desk.db\n")
    stream.write("DESK_DEMO_ACCOUNTS='"+accounts.read_text()+"'\n")
BOOTSTRAP
cat > /etc/systemd/system/launchpad-demo.service <<'SERVICE'
[Unit]
Description=OCI Agent Launchpad synthetic service desk
After=network-online.target
Wants=network-online.target
[Service]
User=launchpad
Group=launchpad
WorkingDirectory=/var/lib/launchpad
EnvironmentFile=/etc/launchpad-demo.env
ExecStart=/opt/launchpad/releases/8c9efdd/venv/bin/python -m uvicorn service_desk.app:create_app --factory --host 127.0.0.1 --port 8092
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/launchpad
[Install]
WantedBy=multi-user.target
SERVICE
systemctl daemon-reload
systemctl enable --now launchpad-demo
systemctl is-active launchpad-demo
