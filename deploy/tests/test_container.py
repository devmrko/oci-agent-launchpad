from pathlib import Path
import sys

import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from prepare_container import prepare
from test_verify_release import result

BASE = 'docker.io/library/python@sha256:' + 'a' * 64


def test_context_contains_only_verified_payload(result, tmp_path):
    (result / '.env').write_text('DO_NOT_COPY=secret')
    output = tmp_path / 'context'
    binding = prepare(result, output, BASE)
    assert binding['app_version'] == '0.4.2'
    assert not (output / '.env').exists()
    assert {p.name for p in output.iterdir()} == {'Dockerfile', '.dockerignore', 'wheels', 'release.json', 'container-input.json'}
    assert 'USER 10001:10001' in (output / 'Dockerfile').read_text()
    with pytest.raises(ValueError, match='already exists'):
        prepare(result, output, BASE)


def test_context_rejects_tampering(result, tmp_path):
    with (result / 'release.zip').open('ab') as stream:
        stream.write(b'tampered')
    with pytest.raises(ValueError, match='checksum'):
        prepare(result, tmp_path / 'context', BASE)
    assert not (tmp_path / 'context').exists()


@pytest.mark.parametrize('image', ['python:3.12-slim', BASE + '\nRUN id', ''])
def test_base_requires_digest(result, tmp_path, image):
    with pytest.raises(ValueError, match='digest-pinned'):
        prepare(result, tmp_path / 'context', image)
