import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import build_release


@pytest.mark.parametrize('value', ['pkg>=1.0\n', 'pkg @ https://example.invalid/a.whl\n', '--extra-index-url https://example.invalid\n', ''])
def test_unpinned_or_remote_requirements_rejected(tmp_path, value):
    lock = tmp_path / 'lock'
    lock.write_text(value)
    with pytest.raises(ValueError, match='exact package pins'):
        build_release.pinned_requirements(lock)


def test_wrong_platform_has_no_output(tmp_path, monkeypatch):
    monkeypatch.setattr(build_release.platform, 'system', lambda: 'Darwin')
    with pytest.raises(ValueError, match='Linux x86_64'):
        build_release.build(tmp_path, 'HEAD', tmp_path, 'HEAD', tmp_path / 'out', 'test')
    assert not (tmp_path / 'out').exists()


def test_source_checksum_failure_never_publishes(tmp_path, monkeypatch):
    monkeypatch.setattr(build_release.sys, 'version_info', (3, 12))
    monkeypatch.setattr(build_release.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(build_release.platform, 'machine', lambda: 'x86_64')
    source = tmp_path / 'untrusted.tgz'
    source.write_bytes(b'not the expected archive')
    with pytest.raises(ValueError, match='checksum mismatch'):
        build_release.build(None, None, tmp_path, None, tmp_path / 'out', 'test', source, '0' * 64)
    assert not (tmp_path / 'out').exists()


def test_direct_network_applies_only_to_pip(monkeypatch):
    calls = []
    monkeypatch.setattr(build_release.subprocess, 'run', lambda args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setenv('LAUNCHPAD_PIP_NETWORK', 'direct')
    monkeypatch.setenv('HTTPS_PROXY', 'http://unreachable.invalid')
    monkeypatch.setenv('PIP_TRUSTED_HOST', 'unsafe.invalid')
    build_release.run('/venv/python', '-m', 'pip', 'install', 'pip==25.3')
    env = calls[-1][1]['env']
    assert 'HTTPS_PROXY' not in env and 'PIP_TRUSTED_HOST' not in env
    assert env['PIP_CONFIG_FILE'] == build_release.os.devnull
    assert env['PIP_INDEX_URL'] == 'https://pypi.org/simple'
    build_release.run('/venv/python', '-m', 'pytest')
    assert 'env' not in calls[-1][1]
    monkeypatch.delenv('LAUNCHPAD_PIP_NETWORK')
    build_release.run('/venv/python', '-m', 'pip', 'install', 'pip==25.3')
    assert 'env' not in calls[-1][1]
