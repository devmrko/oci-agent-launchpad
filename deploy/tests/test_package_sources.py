import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from package_sources import package_sources


def repo(path, files):
    path.mkdir()
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'fixture'], check=True)
    return path


@pytest.fixture
def sources(tmp_path):
    foundation = repo(tmp_path / 'foundation', {'src/lib.py': 'original', 'pyproject.toml': '', 'README.md': '', '.env': 'PRIVATE'})
    launchpad = repo(tmp_path / 'launchpad', {'examples/service-desk/app.py': 'original',
                                           'deploy/package_release.py': '', '.run/token': 'PRIVATE'})
    return foundation, launchpad


def test_only_pinned_sources_and_deterministic_output(tmp_path, sources):
    f, l = sources
    (f / 'src/lib.py').write_text('uncommitted')
    a, b = tmp_path / 'a.tgz', tmp_path / 'b.tgz'
    first = package_sources(f, 'HEAD', l, 'HEAD', a)
    second = package_sources(f, 'HEAD', l, 'HEAD', b)
    assert first == second
    assert a.read_bytes() == b.read_bytes()
    with tarfile.open(a) as archive:
        assert archive.extractfile('foundation/src/lib.py').read() == b'original'
        assert all('.env' not in name and '.run' not in name for name in archive.getnames())
        assert json.load(archive.extractfile('source.json'))['foundation_commit'] == first['foundation_commit']


def test_existing_output_is_not_replaced(tmp_path, sources):
    target = tmp_path / 'existing'
    target.write_bytes(b'keep')
    with pytest.raises(ValueError, match='already exists'):
        package_sources(sources[0], 'HEAD', sources[1], 'HEAD', target)
    assert target.read_bytes() == b'keep'


def test_revision_option_is_rejected(tmp_path, sources):
    with pytest.raises(subprocess.CalledProcessError):
        package_sources(sources[0], '--all', sources[1], 'HEAD', tmp_path / 'invalid')
    assert not (tmp_path / 'invalid').exists()


def test_tracked_secret_under_allowlist_is_rejected(tmp_path, sources):
    f, l = sources
    (l / 'examples/service-desk/.env').write_text('PRIVATE')
    subprocess.run(['git', '-C', str(l), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(l), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'unsafe input'], check=True)
    with pytest.raises(ValueError, match='Private configuration'):
        package_sources(f, 'HEAD', l, 'HEAD', tmp_path / 'invalid')
