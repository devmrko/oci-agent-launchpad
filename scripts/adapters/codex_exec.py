"""Optional Codex CLI adapter; requires an installed, authenticated Codex CLI."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    args = parser.parse_args()
    task = args.task.resolve()
    if not task.is_file():
        parser.error("Task file does not exist")
    executable = shutil.which("codex")
    if executable is None:
        parser.error("Install and authenticate Codex CLI first")
    if any(Path(name).exists() for name in ("CODEX_RESULT.md", "ADAPTER_RESULT.json")):
        parser.error("Use a fresh workspace without previous adapter results")
    prompt = (
        f"Read the task document at {task}. Implement it in the current workspace only. "
        "Read the linked specification, design and tests before editing. "
        "Update implementation, tests, specification and tasks as needed. "
        "Do not access credentials, other projects, external services, or deploy. "
        "Do not create subagents. Run the relevant local tests. "
        "Do not change approval or sandbox settings. "
        "Finish with a short summary of changes, checks and limitations."
    )
    result = subprocess.run([executable, "exec", "--sandbox", "workspace-write", "--ephemeral",
                             "--skip-git-repo-check", "--output-last-message", "CODEX_RESULT.md", prompt], check=False,
                            stdin=subprocess.DEVNULL)
    response = Path("CODEX_RESULT.md")
    has_response = response.is_file() and bool(response.read_text().strip())
    exit_code = result.returncode or (0 if has_response else 3)
    status = "TOOL_FAILED" if result.returncode else ("RESPONSE_RECEIVED" if has_response else "EMPTY_RESPONSE")
    Path("ADAPTER_RESULT.json").write_text(json.dumps({"adapter": "codex-exec", "exit_code": exit_code,
                                                      "tool_exit_code": result.returncode, "status": status,
                                                      "implementation_accepted": False}, indent=2)+"\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
