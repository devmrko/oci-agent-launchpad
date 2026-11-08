import json
import sys
import tarfile
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from package_function_sources import package
from test_package_sources import repo


def sources(tmp_path, dependency='private-library==1.0.0', tools='pytest==9.2.0\n'):
    f = repo(tmp_path / 'f', {'src/library/__init__.py': '', 'README.md': '',
        'pyproject.toml': '[project]\nname="private-library"\nversion="1.0.0"\n'})
    l = repo(tmp_path / 'l', {'examples/service-desk/pyproject.toml':
        '[project]\nname="app"\nversion="1"\ndependencies=["'+dependency+'"]\n',
        'examples/service-desk/requirements-memory.lock': 'packaging==26.3\n',
        'examples/service-desk/tests/test_app.py': 'def test_app(): pass',
        'deploy/function-build-tools.lock': tools, '.env': 'PRIVATE'})
    return f, l


def test_pinned_deterministic_private_source_manifest(tmp_path):
    f, l = sources(tmp_path)
    (f / 'src/library/__init__.py').write_text('uncommitted')
    one, two = tmp_path / 'one.tgz', tmp_path / 'two.tgz'
    first = package(f, 'HEAD', l, 'HEAD', one)
    assert first == package(f, 'HEAD', l, 'HEAD', two)
    assert one.read_bytes() == two.read_bytes()
    with tarfile.open(one) as archive:
        assert archive.extractfile('project/dependencies/foundation/src/library/__init__.py').read() == b''
        assert json.load(archive.extractfile('source.json'))['commit'] == first['commit']
        assert json.load(archive.extractfile('project/build-local.json'))['packages'][0]['name'] == 'private-library'
        assert b'pytest==9.2.0' in archive.extractfile('project/requirements-build.lock').read()
        assert all('.env' not in name for name in archive.getnames())
    with pytest.raises(ValueError, match='already exists'):
        package(f, 'HEAD', l, 'HEAD', one)


@pytest.mark.parametrize('dependency,tools,match', [
    ('private-library==2.0.0', 'pytest==9.2.0', 'does not match'),
    ('private-library==1.0.0', 'packaging==1.0', 'Conflicting'),
    ('private-library==1.0.0', '--extra-index-url https://invalid', 'Exact'),
    ('private-library==1.0.0', 'private-library==1.0.0', 'must come from source'),
])
def test_bad_inputs_never_publish_archive(tmp_path, dependency, tools, match):
    f, l = sources(tmp_path, dependency, tools)
    output = tmp_path / 'out.tgz'
    with pytest.raises(ValueError, match=match):
        package(f, 'HEAD', l, 'HEAD', output)
    assert not output.exists()
