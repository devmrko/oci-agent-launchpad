#!/usr/bin/env bash
set -euo pipefail
app_dir="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$app_dir/../.." && pwd)"
python_bin="${PYTHON:-python3}"
venv_dir="${ENTERPRISE_AI_VENV:-$repo_dir/.run/enterprise-ai-venv}"
"$python_bin" -c 'import sys; sys.exit("Python 3.12 이상이 필요합니다. PYTHON으로 실행 파일을 지정하세요.") if sys.version_info < (3,12) else None'
if [[ ! -f "$venv_dir/pyvenv.cfg" ]]; then
  "$python_bin" -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install -r "$app_dir/requirements.txt"
"$venv_dir/bin/python" -m pip check
printf '\n설치 완료. Python: %s/bin/python\n' "$venv_dir"
printf '실행 전 점검: 위 Python으로 %s/server.py --check를 실행하세요.\n' "$app_dir"
