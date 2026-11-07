#!/usr/bin/env python3
"""Root-only synthetic verification of an allowed, currently active release."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from activate_release import trusted, validate
from register_release import deployment_lock

CONFIG = Path('/etc/launchpad-check.json')
DEPLOYMENT = Path('/etc/launchpad-deployment.json')
SCRIPT = Path('/usr/local/lib/launchpad-checks/check_deployment.py')
LOCK = Path('/run/lock/launchpad-deployment.lock')


def private_json(path):
    trusted(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 65536:
        raise ValueError('Expected root-private JSON file')
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError('Expected JSON object')
    return value


def settings(config, deployment):
    if set(config) != {'allowed_releases', 'credentials_file', 'timeout_seconds'}:
        raise ValueError('Unexpected verifier configuration')
    aliases = config['allowed_releases']
    if not isinstance(aliases, list) or not aliases or len(aliases) > 100 or len(set(aliases)) != len(aliases):
        raise ValueError('Invalid allowed release list')
    for alias in aliases:
        validate(deployment, alias)
    if type(config['timeout_seconds']) is not int or not 30 <= config['timeout_seconds'] <= 240:
        raise ValueError('Verifier timeout must be 30..240 seconds')
    credential_path = Path(config['credentials_file'])
    if not credential_path.is_absolute() or '..' in credential_path.parts:
        raise ValueError('Invalid credential path')


def sudoers(config, deployment):
    settings(config, deployment)
    return 'ocarun ALL=(root) NOPASSWD: ' + ', '.join(
        '/usr/local/sbin/launchpad-check ' + alias for alias in config['allowed_releases']) + '\n'


def run(alias, config_path=CONFIG, deployment_path=DEPLOYMENT, script=SCRIPT, lock_path=LOCK):
    with deployment_lock(lock_path):
        config = private_json(config_path)
        deployment = private_json(deployment_path)
        settings(config, deployment)
        if alias not in config['allowed_releases']:
            raise ValueError('Release not allowed for verification')
        release, version = validate(deployment, alias)
        interpreter = release / 'venv/bin/python'
        trusted(interpreter.parent)
        trusted(interpreter.resolve(strict=True))
        trusted(script)
        trusted(script.with_name('check_runtime.py'))
        # systemctl prints a structured ExecStart description; require an exact path field.
        status = subprocess.run(['/usr/bin/systemctl', 'show', deployment['service'], '--property=ExecStart', '--value'],
                                capture_output=True, text=True, check=True, timeout=10)
        if '{ path=' + str(interpreter) + ' ;' not in status.stdout:
            raise ValueError('Selected release is not active')
        credentials = private_json(Path(config['credentials_file']))
        result = subprocess.run([str(interpreter), '-E', '-s', str(script),
                    '--base-url', 'http://127.0.0.1:' + str(deployment['port']),
                    '--expected-version', version, '--credentials-stdin'],
                    input=json.dumps(credentials), capture_output=True, text=True,
                    timeout=config['timeout_seconds'], env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        if result.returncode:
            raise RuntimeError('Post-deployment verification failed')
        report = json.loads(result.stdout)
        if report.get('result') != 'PASS' or report.get('version') != version:
            raise RuntimeError('Unexpected verification result')
        telemetry = report['telemetry']
        if telemetry.get('chat_input_output') is not True or telemetry.get('memory_content_excluded') is not True:
            raise RuntimeError('Incomplete telemetry verification')
        # Project only known, non-sensitive summary fields; never forward arbitrary stdout.
        return {'result': 'PASS', 'release_alias': alias, 'version': version,
                'checks': ['active-release', 'model-memory-runtime', 'langfuse-input-output', 'memory-body-excluded'],
                'observations': telemetry['observations']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', nargs='?')
    parser.add_argument('--sudoers', action='store_true', help='Root administrator: print exact allowed commands')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Root required')
    if args.sudoers:
        print(sudoers(private_json(CONFIG), private_json(DEPLOYMENT)), end='')
        return 0
    if args.release is None:
        parser.error('Release alias required')
    try:
        print(json.dumps(run(args.release)))
        return 0
    except Exception:
        print(json.dumps({'result': 'FAIL', 'reason': 'Verifier failed; check allowed/active release, private configuration and dependency health'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
