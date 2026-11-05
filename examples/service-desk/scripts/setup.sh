#!/usr/bin/env bash
set -euo pipefail
example="$(cd "$(dirname "$0")/.." && pwd)"
foundation="${1:?Usage: bash scripts/setup.sh /path/to/python-foundation}"
expected=c98f69dd20c005ac5aa244dd03f110ddeed368dd
[[ "$(git -C "$foundation" rev-parse HEAD)" == "$expected" ]] || { echo "Foundation commit mismatch: expected $expected" >&2; exit 1; }
git -C "$foundation" diff --quiet HEAD -- src pyproject.toml || { echo "Foundation source has local changes" >&2; exit 1; }
"${PYTHON:-python3}" -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ required; set PYTHON to a compatible executable"'
if [[ -x "$example/.venv/bin/python" ]]; then
  "$example/.venv/bin/python" -c 'import sys; assert sys.version_info >= (3, 12), "Existing .venv uses old Python; move it aside before setup"'
fi
"${PYTHON:-python3}" -m venv "$example/.venv"
"$example/.venv/bin/python" -m pip install "$foundation" -r "$example/requirements.lock"
"$example/.venv/bin/python" -m pip install --no-deps -e "$example"
