"""Run an explicitly selected command in a copy of a spec-linked workspace (POSIX)."""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess

from developer_handoff import inspect
from requirement_handoff import read, write_new
from spec_impact import local


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(workspace):
    result = {}
    total = 0
    for path in sorted(workspace.rglob("*")):
        relative = path.relative_to(workspace)
        if any(part in {"__pycache__", ".git"} for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("Symlink output is not supported")
        if path.is_file():
            if path.stat().st_size > 1024 * 1024 or len(result) >= 200:
                raise ValueError("Output exceeds collection limits")
            data = path.read_bytes()
            total += len(data)
            if total > 8 * 1024 * 1024:
                raise ValueError("Output exceeds collection limits")
            result[relative.as_posix()] = data
        elif not path.is_dir():
            raise ValueError("Nonregular output is not supported")
    return result


def run(root, handoff, output, command, timeout=300):
    root, handoff, output = Path(root).resolve(), Path(handoff), Path(output)
    if os.name != "posix" or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("POSIX and positive finite timeout required")
    if not command or not all(isinstance(arg, str) and arg for arg in command):
        raise ValueError("Explicit command required")
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be new")
    baseline = read(handoff / "baseline.json")
    if inspect(root, baseline)["status"] != "UNCHANGED":
        raise ValueError("Handoff baseline is stale")
    task_path = handoff / "TASK.md"
    if task_path.is_symlink() or not task_path.is_file() or task_path.stat().st_size > 1024 * 1024:
        raise ValueError("Invalid task document")
    task = task_path.read_bytes()
    sources = {}
    for name, expected in baseline["files"].items():
        path = local(root, name)
        if path.is_symlink():
            raise ValueError("Source symlink")
        sources[name] = path.read_bytes()
        if digest(sources[name]) != expected:
            raise ValueError("Source changed before copying")
    output.mkdir(mode=0o700)
    output = output.resolve()
    workspace = output / "workspace"
    workspace.mkdir(mode=0o700)
    for name, data in sources.items():
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    task_copy = output / "TASK.md"
    task_copy.write_bytes(task)
    before = snapshot(workspace)
    argv = [arg.replace("{task}", str(task_copy)).replace("{workspace}", str(workspace)) for arg in command]
    write_new(output / "status.json", {"status": "RUNNING"})
    code, state = None, "START_FAILED"
    process = None
    try:
        process = subprocess.Popen(argv, cwd=workspace, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
            state = "COMMAND_SUCCEEDED" if code == 0 else "COMMAND_FAILED"
        except subprocess.TimeoutExpired:
            state = "TIMED_OUT"
    except OSError:
        state = "START_FAILED"
    except KeyboardInterrupt:
        state = "INTERRUPTED"
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    changed, patch = [], []
    collection = "COLLECTED"
    try:
        after = snapshot(workspace)
        for name in sorted(before.keys() | after.keys()):
            old, new = before.get(name), after.get(name)
            if old == new:
                continue
            changed.append({"path": name, "kind": "added" if old is None else "deleted" if new is None else "modified",
                            "before_sha256": digest(old) if old is not None else None,
                            "after_sha256": digest(new) if new is not None else None})
            try:
                lines = difflib.unified_diff((old or b"").decode().splitlines(keepends=True),
                                                 (new or b"").decode().splitlines(keepends=True),
                                                 fromfile=f"before/{name}", tofile=f"after/{name}")
                for line in lines:
                    patch.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
            except UnicodeDecodeError:
                patch.append(f"Binary file changed: {name}\n")
    except (OSError, ValueError):
        collection = "COLLECTION_FAILED"
    result = {"schema_version": 1, "status": state, "exit_code": code, "collection": collection,
              "recorded_at": datetime.now(timezone.utc).isoformat(), "changed_files": changed,
              "tests_executed": False, "implementation_accepted": False, "automatic_apply_performed": False}
    (output / "changes.diff").write_text("".join(patch), encoding="utf-8")
    write_new(output / "run.json", result)
    write_new(output / "status-final.json", {"status": state, "collection": collection})
    (output / "status-final.json").replace(output / "status.json")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Append -- COMMAND ARGS; placeholders: {task}, {workspace}")
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    # Parse the command separately so ordinary options may follow the handoff path.
    import sys
    arguments = sys.argv[1:]
    if arguments in (["--help"], ["-h"]):
        parser.print_help()
        return 0
    if "--" not in arguments:
        parser.error("Specify an explicit command after --")
    boundary = arguments.index("--")
    command = arguments[boundary + 1:]
    args = parser.parse_args(arguments[:boundary])
    try:
        result = run(args.root, args.handoff, args.output, command, args.timeout)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Runner preparation failed; check current handoff, paths, command and new output.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMMAND_SUCCEEDED" and result["collection"] == "COLLECTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
