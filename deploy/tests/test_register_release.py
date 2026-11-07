import hashlib
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
import register_release as registration
from test_prepare_release import inputs, call
from test_verify_release import result


@pytest.fixture
def setup(result, inputs, tmp_path, monkeypatch):
    prepared = tmp_path / 'prepared'
    receipt = call(result, inputs, prepared)
    config = inputs[1]
    sudoers = tmp_path / 'sudoers'
    sudoers.write_bytes(b'old sudoers\n')
    lock = tmp_path / 'lock'
    monkeypatch.setattr(registration, 'trusted', lambda path: None)
    monkeypatch.setattr(registration, 'instance_identity', lambda: receipt['target'])
    monkeypatch.setattr(registration, 'validate_sudoers', lambda raw, directory: None)
    real_stat = registration.os.fstat
    def root_stat(fd):
        value = real_stat(fd)
        fields = list(value)
        fields[4] = 0
        return registration.os.stat_result(fields)
    monkeypatch.setattr(registration.os, 'fstat', root_stat)
    def run():
        sha = hashlib.sha256((prepared / 'preparation.json').read_bytes()).hexdigest()
        return registration.register(prepared, sha, config, sudoers, lock)
    return prepared, config, sudoers, lock, run


def rewrite_receipt(prepared, **changes):
    path = prepared / 'preparation.json'
    value = json.loads(path.read_text())
    value.update(changes)
    path.write_text(json.dumps(value))


def rehash_candidate(prepared):
    receipt = json.loads((prepared / 'preparation.json').read_text())
    receipt['files']['deployment.json'] = hashlib.sha256((prepared / 'deployment.json').read_bytes()).hexdigest()
    rewrite_receipt(prepared, files=receipt['files'])


def test_register_preserves_old_and_adds_only_new(setup):
    prepared, config, sudoers, _, run = setup
    old = json.loads(config.read_text())
    assert run()['status'] == 'REGISTERED'
    new = json.loads(config.read_text())
    assert new['releases']['old'] == old['releases']['old']
    assert new == json.loads((prepared / 'deployment.json').read_text())
    assert b'launchpad-deploy new' in sudoers.read_bytes()
    assert config.stat().st_mode & 0o777 == 0o600
    assert sudoers.stat().st_mode & 0o777 == 0o440


def test_second_registration_requires_fresh_preparation(setup):
    *_, run = setup
    run()
    with pytest.raises(ValueError, match='changed'):
        run()


def test_identical_alias_does_not_write(setup, monkeypatch):
    prepared, config, sudoers, _, run = setup
    config.write_bytes((prepared / 'deployment.json').read_bytes())
    rewrite_receipt(prepared, previous_vm_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest())
    monkeypatch.setattr(registration, 'replace_file', lambda *args: pytest.fail('unexpected write'))
    assert run()['status'] == 'UNCHANGED'
    assert sudoers.read_bytes() == b'old sudoers\n'


def test_stale_configuration_is_preserved(setup):
    _, config, sudoers, _, run = setup
    config.write_text(config.read_text() + '\n')
    before = config.read_bytes()
    with pytest.raises(ValueError, match='changed'):
        run()
    assert config.read_bytes() == before
    assert sudoers.read_bytes() == b'old sudoers\n'


@pytest.mark.parametrize('field', ['port', 'old', 'delete'])
def test_rehashed_changes_cannot_alter_existing_settings(setup, field):
    prepared, config, sudoers, _, run = setup
    path = prepared / 'deployment.json'
    candidate = json.loads(path.read_text())
    if field == 'port':
        candidate['port'] = 8093
    elif field == 'old':
        candidate['releases']['old']['version'] = '9.9'
    else:
        del candidate['releases']['old']
    path.write_text(json.dumps(candidate))
    rehash_candidate(prepared)
    with pytest.raises(ValueError, match='preserve'):
        run()
    assert sudoers.read_bytes() == b'old sudoers\n'


def test_wrong_vm(setup, monkeypatch):
    *_, run = setup
    monkeypatch.setattr(registration, 'instance_identity', lambda: {'instance_id': 'wrong', 'compartment_id': 'wrong'})
    with pytest.raises(ValueError, match='target'):
        run()


@pytest.mark.parametrize('name', ['deployment.json', 'release.tfvars.json'])
def test_tampered_prepared_file(setup, name):
    prepared, *_, run = setup
    path = prepared / name
    path.write_text(path.read_text() + '\n')
    with pytest.raises(ValueError, match='checksum'):
        run()


def test_receipt_is_bound_to_external_digest(setup):
    prepared, config, sudoers, lock, _ = setup
    with pytest.raises(ValueError, match='receipt checksum'):
        registration.register(prepared, '0'*64, config, sudoers, lock)


def test_visudo_failure_makes_no_changes(setup, monkeypatch):
    _, config, sudoers, _, run = setup
    before = config.read_bytes()
    def fail(*args):
        raise RuntimeError('visudo failed')
    monkeypatch.setattr(registration, 'validate_sudoers', fail)
    with pytest.raises(RuntimeError, match='visudo'):
        run()
    assert config.read_bytes() == before
    assert sudoers.read_bytes() == b'old sudoers\n'


def test_config_write_failure_restores_sudoers(setup, monkeypatch):
    _, config, sudoers, _, run = setup
    before = config.read_bytes()
    replace = registration.replace_file
    def fail(path, raw, mode):
        if path == config:
            raise OSError('disk failed')
        replace(path, raw, mode)
    monkeypatch.setattr(registration, 'replace_file', fail)
    with pytest.raises(OSError, match='disk failed'):
        run()
    assert config.read_bytes() == before
    assert sudoers.read_bytes() == b'old sudoers\n'


def test_competing_lock_makes_no_changes(setup):
    _, config, sudoers, lock, run = setup
    with registration.deployment_lock(lock):
        with pytest.raises(BlockingIOError):
            run()
    assert sudoers.read_bytes() == b'old sudoers\n'


def test_lock_symlink_is_rejected(setup):
    _, config, _, lock, run = setup
    lock.symlink_to(config)
    with pytest.raises(OSError):
        run()
