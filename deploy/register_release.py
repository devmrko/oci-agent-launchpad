#!/usr/bin/env python3
"""Register one prepared release on its OCI VM without restarting the app."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import urllib.request

from activate_release import trusted
from prepare_release import read_object, settings
from verify_release import digest

CONFIG = Path('/etc/launchpad-deployment.json')
SUDOERS = Path('/etc/sudoers.d/launchpad-deploy')
LOCK = Path('/run/lock/launchpad-deployment.lock')


def instance_identity():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request('http://169.254.169.254/opc/v2/instance/',
                                     headers={'Authorization': 'Bearer Oracle'})
    with opener.open(request, timeout=5) as response:
        metadata = json.load(response)
    return {'instance_id': metadata['id'], 'compartment_id': metadata['compartmentId']}


@contextmanager
def deployment_lock(path):
    trusted(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Untrusted deployment lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def replace_file(path, raw, mode):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sudoers_content(config):
    commands = []
    for alias, release in config['releases'].items():
        commands.append('/usr/local/sbin/launchpad-activate ' + alias)
        if 'manifest_sha256' in release:
            commands.append('/usr/local/sbin/launchpad-deploy ' + alias)
    return ('ocarun ALL=(root) NOPASSWD: ' + ', '.join(commands) + '\n').encode()


def validate_sudoers(raw, directory):
    fd, name = tempfile.mkstemp(prefix='.launchpad-check-', dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o440)
            stream.write(raw)
        subprocess.run(['/usr/sbin/visudo', '-cf', str(temporary)], check=True,
                       capture_output=True, timeout=10)
    finally:
        temporary.unlink(missing_ok=True)


def load_prepared(prepared, expected_hash):
    digest(expected_hash)
    names = ('preparation.json', 'deployment.json', 'release.tfvars.json')
    for name in names:
        trusted(prepared / name)
    receipt, actual_hash = read_object(prepared / names[0])
    if actual_hash != expected_hash:
        raise ValueError('Preparation receipt checksum mismatch')
    if receipt.get('schema_version') != 1 or receipt.get('status') != 'READY':
        raise ValueError('Preparation not READY')
    candidate, candidate_hash = read_object(prepared / names[1])
    variables, variables_hash = read_object(prepared / names[2])
    if receipt.get('files') != {names[1]: candidate_hash, names[2]: variables_hash}:
        raise ValueError('Prepared configuration checksum mismatch')
    settings(variables, candidate)
    alias = receipt['release_alias']
    if variables['release_alias'] != alias or variables['manifest_sha256'] != receipt['manifest_sha256']:
        raise ValueError('Prepared release identity mismatch')
    digest(receipt['manifest_sha256'])
    digest(receipt['previous_vm_config_sha256'])
    if candidate['releases'].get(alias) != {'directory': alias, 'version': variables['app_version'],
                                          'manifest_sha256': receipt['manifest_sha256']}:
        raise ValueError('Prepared release entry mismatch')
    if receipt['target'] != {k: variables[k] for k in ('region', 'compartment_id', 'project_id', 'instance_id')}:
        raise ValueError('Prepared target mismatch')
    return receipt, candidate


def register(prepared, expected_hash, config_path=CONFIG, sudoers_path=SUDOERS, lock_path=LOCK):
    receipt, candidate = load_prepared(prepared, expected_hash)
    identity = instance_identity()
    if any(identity[k] != receipt['target'][k] for k in ('instance_id', 'compartment_id')):
        raise ValueError('This VM is not the prepared target')
    with deployment_lock(lock_path):
        trusted(config_path)
        trusted(sudoers_path)
        current, current_hash = read_object(config_path)
        if current_hash != receipt['previous_vm_config_sha256']:
            raise ValueError('VM configuration changed; prepare again from latest configuration')
        alias = receipt['release_alias']
        expected = dict(current)
        expected['releases'] = dict(current['releases'])
        if alias in expected['releases'] and expected['releases'][alias] != candidate['releases'][alias]:
            raise ValueError('Cannot change an existing release')
        expected['releases'][alias] = candidate['releases'][alias]
        if candidate != expected:
            raise ValueError('Only the prepared release may be added; preserve existing settings and releases')
        if current == candidate:
            return {'status': 'UNCHANGED', 'release_alias': alias, 'app_restarted': False}
        previous_sudoers = sudoers_path.read_bytes()
        previous_mode = stat.S_IMODE(sudoers_path.stat().st_mode)
        new_sudoers = sudoers_content(candidate)
        validate_sudoers(new_sudoers, sudoers_path.parent)
        # Old configuration denies the new alias until the second replacement succeeds.
        replace_file(sudoers_path, new_sudoers, 0o440)
        try:
            replace_file(config_path, (json.dumps(candidate, indent=2) + '\n').encode(), 0o600)
        except Exception:
            replace_file(sudoers_path, previous_sudoers, previous_mode)
            raise
        return {'status': 'REGISTERED', 'release_alias': alias, 'app_restarted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--receipt-sha256', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Root required')
    print(json.dumps(register(args.prepared, args.receipt_sha256)))


if __name__ == '__main__':
    main()
