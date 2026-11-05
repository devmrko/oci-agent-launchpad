#!/usr/bin/env bash
set -euo pipefail
release=/opt/launchpad/releases/memory-0.3.0
backup=/opt/launchpad/backups/pre-memory-0.3.0
install -d "$release"
cp "${1:-/tmp/requirements-memory.lock}" "$release/requirements.lock"
python3.12 -m venv "$release/venv"
"$release/venv/bin/pip" install -r "$release/requirements.lock" /tmp/devmrko_python_foundation-0.1.2-py3-none-any.whl /tmp/launchpad_service_desk-0.3.0-py3-none-any.whl
"$release/venv/bin/pip" check
if [[ ! -d "$backup" ]]; then
  install -d -m 700 "$backup"
  cp -p /etc/launchpad-demo.env "$backup/environment"
  cp -p /etc/systemd/system/launchpad-demo.service "$backup/service"
fi
sed -i '\|^DESK_MEMORY_CONFIG=|d' /etc/launchpad-demo.env
printf '%s\n' 'DESK_MEMORY_CONFIG=/etc/launchpad-memory.json' >> /etc/launchpad-demo.env
sed -i 's|^ExecStart=.*|ExecStart=/opt/launchpad/releases/memory-0.3.0/venv/bin/python -m uvicorn service_desk.app:create_app --factory --host 127.0.0.1 --port 8092|' /etc/systemd/system/launchpad-demo.service
systemctl daemon-reload
systemctl restart launchpad-demo
if ! curl --silent --fail --retry 20 --retry-connrefused --retry-delay 1 http://127.0.0.1:8092/health; then
  cp -p "$backup/environment" /etc/launchpad-demo.env
  cp -p "$backup/service" /etc/systemd/system/launchpad-demo.service
  systemctl daemon-reload
  systemctl restart launchpad-demo
  exit 1
fi
systemctl is-active launchpad-demo
