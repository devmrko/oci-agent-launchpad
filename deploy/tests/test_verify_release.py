import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from package_release import package
from verify_release import deployment_inputs, validate_result


@pytest.fixture
def result(tmp_path):
    wheels = tmp_path / 'wheels'
    wheels.mkdir()
    for name, version in [('launchpad_service_desk', '0.4.2'), ('devmrko_python_foundation', '0.1.2')]:
        with zipfile.ZipFile(wheels / f'{name}-{version}-py3-none-any.whl', 'w') as wheel:
            wheel.writestr(f'{name}-{version}.dist-info/METADATA', f'Name: {name}\nVersion: {version}\n')
    req = tmp_path / 'req'
    req.write_text('launchpad-service-desk==0.4.2\ndevmrko-python-foundation==0.1.2\n')
    root = tmp_path / 'result'; root.mkdir()
    hashes = package(wheels, req, root / 'release.zip')
    metadata = {'schema_version': 1, 'build_id': 'test-build', 'foundation_commit': 'a'*40,
                'launchpad_commit': 'b'*40, 'source_sha256': 'c'*64, 'app_version': '0.4.2',
                'foundation_version': '0.1.2', 'target': {'os':'linux','architecture':'x86_64','python':'3.12'},
                'verification': {'dependency_check':'passed','imports':'passed','example_tests':'passed'}, **hashes}
    (root / 'release.json').write_text(json.dumps(metadata))
    return root


def test_build_provenance_drives_deployment_inputs(result):
    metadata = validate_result(result)
    data = deployment_inputs(result, {'region':'ap-seoul-1','app_version':'incorrect'})
    assert data['app_version'] == '0.4.2'
    assert data['manifest_sha256'] == metadata['manifest_sha256']
    assert data['release_alias'].startswith('memory-0.4.2-')
    assert data['region'] == 'ap-seoul-1'


def test_tampered_bundle_cannot_be_deployed(result):
    with (result / 'release.zip').open('ab') as stream: stream.write(b'modified')
    with pytest.raises(ValueError, match='Bundle checksum'):
        deployment_inputs(result, {})


@pytest.mark.parametrize('field,value,message', [
    ('app_version','9.9.9','Wheel version'),
    ('manifest_sha256','0'*64,'Manifest checksum'),
    ('verification',{'example_tests':'failed'},'verification'),
    ('target',{'os':'darwin'},'target'),
])
def test_false_metadata_cannot_pass(result, field, value, message):
    path=result/'release.json'; data=json.loads(path.read_text());data[field]=value;path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=message): validate_result(result)


def test_unsafe_release_alias_is_rejected(result):
    with pytest.raises(ValueError, match='alias'): deployment_inputs(result, {}, '../escape')
