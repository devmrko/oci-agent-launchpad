from unittest.mock import Mock
import io
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from fetch_build_result import fetch


def test_failed_build_is_not_downloaded(tmp_path):
    devops, content = Mock(), Mock()
    devops.get_build_run.return_value.data.lifecycle_state = 'FAILED'
    with pytest.raises(ValueError, match='not succeeded'):
        fetch(devops, content, 'run', 'repo', 'version', tmp_path / 'result')
    content.get_generic_artifact_content_by_path.assert_not_called()
    assert not (tmp_path / 'result').exists()


def test_artifact_from_other_build_is_not_published(tmp_path):
    devops, content = Mock(), Mock()
    devops.get_build_run.return_value.data.lifecycle_state = 'SUCCEEDED'
    content.get_generic_artifact_content_by_path.return_value.data.raw.stream.return_value = [json.dumps({'build_id':'other'}).encode()]
    with pytest.raises(ValueError, match='different build'):
        fetch(devops, content, 'run', 'repo', 'version', tmp_path / 'result')
    assert content.get_generic_artifact_content_by_path.call_count == 1
    assert not (tmp_path / 'result').exists()


from test_verify_release import result


def test_verified_build_download_is_published(result, tmp_path):
    devops, content = Mock(), Mock()
    devops.get_build_run.return_value.data.lifecycle_state = 'SUCCEEDED'
    def download(repository, name, version):
        response = Mock()
        response.data.raw.stream.return_value = [(result / name).read_bytes()]
        return response
    content.get_generic_artifact_content_by_path.side_effect = download
    target = tmp_path / 'downloaded'
    metadata = fetch(devops, content, 'test-build', 'repo', 'v1', target)
    assert metadata['app_version'] == '0.4.2'
    assert (target / 'release.zip').read_bytes() == (result / 'release.zip').read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        fetch(devops, content, 'test-build', 'repo', 'v1', target)
