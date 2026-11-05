#!/usr/bin/env bash
# Run as root on the new Oracle Linux demo VM, after cloud-init completes.
set -euo pipefail
archive="${1:?source archive required}"
backup=/opt/launchpad/backups/pre-2669f0d
if [[ -f /etc/systemd/system/launchpad-demo.service && ! -d "$backup" ]]; then
  install -d -m 700 "$backup"
  cp -p /etc/systemd/system/launchpad-demo.service "$backup/service"
  cp -p /etc/launchpad-demo.env "$backup/environment"
fi
release=/opt/launchpad/releases/2669f0d
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
if [[ -n "${2:-}" ]]; then cat "$2" >> /etc/launchpad-demo.env; fi
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
ExecStart=/opt/launchpad/releases/2669f0d/venv/bin/python -m uvicorn service_desk.app:create_app --factory --host 127.0.0.1 --port 8092
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
systemctl enable launchpad-demo
systemctl restart launchpad-demo
if ! curl --silent --fail --retry 15 --retry-connrefused --retry-delay 1 http://127.0.0.1:8092/health; then
  if [[ -f "$backup/service" ]]; then
    cp -p "$backup/service" /etc/systemd/system/launchpad-demo.service
    cp -p "$backup/environment" /etc/launchpad-demo.env
    systemctl daemon-reload
    systemctl restart launchpad-demo
  fi
  exit 1
fi
systemctl is-active launchpad-demo
