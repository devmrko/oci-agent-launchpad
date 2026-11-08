import json
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace
import sys
import stat
from unittest.mock import Mock

import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from build_capacity import preflight
from build_container import build


def entry(path, gib):
    return {'path': str(path), 'plan': {'schema_version': 1, 'role': 'synthetic-build', 'reserve_gib': 1,
            'components': [{'name': 'work', 'phase': 'transient', 'gib': gib, 'copies': 1, 'basis': 'test fixture'}]}}


def test_same_filesystem_budgets_are_added(tmp_path, monkeypatch):
    one = tmp_path / 'context'; one.mkdir()
    two = tmp_path / 'docker'; two.mkdir()
    usage = namedtuple('usage', 'total used free')
    monkeypatch.setattr('build_capacity.shutil.disk_usage', lambda p: usage(100*1024**3, 90*1024**3, 10*1024**3))
    assert preflight([entry(one, 6)])['result'] == 'PASS'
    assert preflight([entry(two, 6)])['result'] == 'PASS'
    combined = preflight([entry(one, 6), entry(two, 6)])
    assert combined['result'] == 'INSUFFICIENT'
    assert combined['filesystems'][0]['required_free_gib'] == 13


def test_insufficient_space_never_starts_docker_build(tmp_path, monkeypatch):
    context = tmp_path / 'context'; context.mkdir()
    root = tmp_path / 'docker'; root.mkdir()
    (context / 'container-input.json').write_text(json.dumps({'platform': 'linux/amd64', 'base_image': 'python@sha256:' + 'a'*64}))
    monkeypatch.setattr('build_container.platform.system', lambda: 'Linux')
    original = Path.stat
    monkeypatch.setattr(Path, 'stat', lambda self, **kw: SimpleNamespace(st_mode=stat.S_IFSOCK) if str(self) == '/var/run/docker.sock' else original(self, **kw))
    monkeypatch.setattr('build_container.preflight', lambda entries: {'result': 'INSUFFICIENT'})
    runner = Mock(return_value=SimpleNamespace(stdout=json.dumps({'DockerRootDir': str(root)})))
    with pytest.raises(ValueError, match='aggregate'):
        build(context, {'storage': [entry(context, 6), entry(root, 6)]}, 'launchpad:test', run=runner)
    assert runner.call_count == 1
    assert runner.call_args.args[0][3] == 'info'


def test_local_driver_build_uses_fixed_endpoint_and_pinned_base(tmp_path, monkeypatch):
    context = tmp_path / 'context'; context.mkdir()
    root = tmp_path / 'docker'; root.mkdir()
    base = 'python@sha256:' + 'a'*64
    (context / 'container-input.json').write_text(json.dumps({'platform': 'linux/amd64', 'base_image': base}))
    monkeypatch.setattr('build_container.platform.system', lambda: 'Linux')
    original = Path.stat
    monkeypatch.setattr(Path, 'stat', lambda self, **kw: SimpleNamespace(st_mode=stat.S_IFSOCK) if str(self) == '/var/run/docker.sock' else original(self, **kw))
    monkeypatch.setattr('build_container.preflight', lambda entries: {'result': 'PASS'})
    monkeypatch.setenv('DOCKER_HOST', 'tcp://unrelated.invalid:2375')
    monkeypatch.setenv('BUILDX_BUILDER', 'unrelated')
    runner = Mock(side_effect=[SimpleNamespace(stdout=json.dumps({'DockerRootDir': str(root)})),
                               SimpleNamespace(stdout='Name: default\nDriver: docker\n'), SimpleNamespace()])
    build(context, {'storage': [entry(context, 6), entry(root, 6)]}, 'launchpad:test', run=runner)
    command = runner.call_args.args[0]
    assert command[:5] == ['docker', '--host', 'unix:///var/run/docker.sock', 'buildx', 'build']
    assert 'BASE_IMAGE=' + base in command
    assert '--load' in command
    assert 'DOCKER_HOST' not in runner.call_args.kwargs['env']
    assert 'BUILDX_BUILDER' not in runner.call_args.kwargs['env']
