"""Record explicit project command results without claiming requirement coverage (POSIX)."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

from requirement_handoff import read


def local(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('Expected a project-relative file')
    path = root / name
    if '..' in Path(name).parts or not path.resolve().is_relative_to(root):
        raise ValueError('External path')
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('Missing file or symlink')
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('File exceeds 8 MiB')
    return path


def snapshot(root, plan):
    root = Path(root).resolve()
    path = local(root, plan)
    data = read(path)
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Unsupported plan')
    spec = local(root, data['spec'])
    ids = re.findall(r'^## (REQ-\d+)\b', spec.read_text(), re.M)
    selected, files = data['requirements'], data['files']
    if (not ids or len(ids) != len(set(ids)) or not isinstance(selected, list) or not selected
            or not all(isinstance(x, str) for x in selected)
            or len(selected) != len(set(selected)) or not set(selected) <= set(ids)):
        raise ValueError('Invalid requirement references')
    if (not isinstance(files, list) or not files or len(files) > 200
            or not all(isinstance(x, str) for x in files) or len(files) != len(set(files))):
        raise ValueError('Invalid files')
    paths = {local(root, name).relative_to(root).as_posix() for name in files}
    paths.update([path.relative_to(root).as_posix(), spec.relative_to(root).as_posix()])
    return {'requirements': selected, 'files': {
        name: hashlib.sha256(local(root, name).read_bytes()).hexdigest() for name in sorted(paths)}}


def inspect(root, evidence):
    if (not isinstance(evidence, dict) or evidence.get('kind') != 'command_evidence' or evidence.get('schema_version') != 1
            or not isinstance(evidence.get('files'), dict) or not evidence['files']):
        raise ValueError('Not command evidence')
    try:
        current = snapshot(root, evidence['plan'])
        changed = sorted(name for name in current['files'].keys() | evidence['files'].keys()
                         if current['files'].get(name) != evidence['files'].get(name))
        freshness = 'STALE' if changed else 'CURRENT'
    except (OSError, ValueError, KeyError, TypeError):
        changed, freshness = [], 'INVALID'
    return {'freshness': freshness, 'changed_files': changed,
            'usable_command_success': freshness == 'CURRENT' and evidence.get('status') == 'COMMAND_SUCCEEDED'
                and evidence.get('exit_code') == 0 and evidence.get('stable_during_run') is True,
            'requirements_verified': False, 'command_executed': False}


def execute(root, plan, output, command, timeout=300):
    root, output = Path(root).resolve(), Path(output)
    if os.name != 'posix' or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('POSIX and positive finite timeout required')
    if not command or not all(isinstance(arg, str) and arg and '\0' not in arg for arg in command):
        raise ValueError('Explicit argv required')
    before = snapshot(root, plan)
    # Reserve the result before executing; do not run if it cannot be written.
    with open(output, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump({'kind': 'command_evidence', 'schema_version': 1, 'status': 'RUNNING'}, stream)
    process, code, state = None, None, 'START_FAILED'
    try:
        process = subprocess.Popen(command, cwd=root, shell=False, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
            state = 'COMMAND_SUCCEEDED' if code == 0 else 'COMMAND_FAILED'
        except subprocess.TimeoutExpired:
            state = 'TIMED_OUT'
    except OSError:
        state = 'START_FAILED'
    except KeyboardInterrupt:
        state = 'INTERRUPTED'
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    try:
        stable = snapshot(root, plan) == before
    except (OSError, ValueError, KeyError, TypeError):
        stable = False
    result = {'kind': 'command_evidence', 'schema_version': 1,
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'plan': plan,
              'command': command, 'status': state, 'exit_code': code,
              'stable_during_run': stable, **before, 'requirements_verified': False}
    # The reserved file is local evidence, not a signed record or a sandbox boundary.
    if output.is_symlink():
        raise ValueError('Output replaced by symlink')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run')
    run.add_argument('plan')
    run.add_argument('--output', required=True, type=Path)
    run.add_argument('--timeout', type=float, default=300)
    check = sub.add_parser('check')
    check.add_argument('evidence', type=Path)
    for part in (run, check):
        part.add_argument('--root', type=Path, default=Path.cwd())
    args_list = sys.argv[1:]
    boundary = args_list.index('--') if '--' in args_list else len(args_list)
    args = parser.parse_args(args_list[:boundary])
    command = args_list[boundary+1:]
    try:
        if args.action == 'run':
            result = execute(args.root, args.plan, args.output, command, args.timeout)
            success = result['status'] == 'COMMAND_SUCCEEDED' and result['stable_during_run']
        else:
            if command:
                raise ValueError('Check does not execute commands')
            result = inspect(args.root, read(args.evidence))
            success = result['usable_command_success']
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, 'Invalid plan, command, evidence or output path.\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(main())
