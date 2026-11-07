from collections import namedtuple
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from capacity_plan import calculate, check, GIB


def plan():
    return {'schema_version': 1, 'role': 'test-builder', 'reserve_gib': 5, 'components': [
        {'name': 'os-stack', 'phase': 'resident', 'gib': 10, 'copies': 1, 'basis': 'test observation'},
        {'name': 'retained-images', 'phase': 'growth', 'gib': 4, 'copies': 2, 'basis': 'test estimate'},
        {'name': 'build-workspaces', 'phase': 'transient', 'gib': 6, 'copies': 2, 'basis': 'test peak'}]}


def test_concurrent_peak_and_retention_are_counted():
    result = calculate(plan())
    assert result['required_filesystem_gib'] == 35
    assert result['required_free_gib'] == 25


def test_actual_free_space_is_checked_not_just_provisioned_size(monkeypatch, tmp_path):
    Usage = namedtuple('Usage', 'total used free')
    monkeypatch.setattr('capacity_plan.shutil.disk_usage', lambda p: Usage(100*GIB, 80*GIB, 20*GIB))
    assert check(plan(), tmp_path)['result'] == 'INSUFFICIENT'
    monkeypatch.setattr('capacity_plan.shutil.disk_usage', lambda p: Usage(100*GIB, 70*GIB, 30*GIB))
    assert check(plan(), tmp_path)['result'] == 'PASS'


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True])
def test_invalid_budget_rejected(value):
    data = plan(); data['components'][0]['gib'] = value
    with pytest.raises(ValueError): calculate(data)


def test_missing_assumptions_rejected():
    data = plan(); data['components'][0]['basis'] = ''
    with pytest.raises(ValueError): calculate(data)


def test_sdk_provisioning_rejects_budget_before_any_oci_access(tmp_path, monkeypatch):
    import json
    import runpy
    from types import SimpleNamespace, ModuleType
    from unittest.mock import Mock
    import sys
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'runtime_capacity_plan': plan(), 'boot_volume_gb': 10}))
    api = Mock(side_effect=AssertionError('OCI must not be contacted'))
    fake = ModuleType('oci')
    fake.config = SimpleNamespace(from_file=api)
    core = ModuleType('oci.core'); core.models = SimpleNamespace()
    fake.core = core
    monkeypatch.setitem(sys.modules, 'oci', fake)
    monkeypatch.setitem(sys.modules, 'oci.core', core)
    monkeypatch.setattr(sys, 'argv', ['provision_demo.py', '--config', str(config), '--state', str(tmp_path / 'state.json')])
    with pytest.raises(ValueError, match='boot_volume_gb'):
        runpy.run_path(str(Path(__file__).parents[1] / 'provision_demo.py'), run_name='__main__')
    api.assert_not_called()
    assert not (tmp_path / 'state.json').exists()


def test_provisioning_conversion_matches_terraform():
    from capacity_plan import validate_provisioning
    with pytest.raises(ValueError):
        validate_provisioning({'runtime_capacity_plan': plan(), 'boot_volume_gb': 37})
    assert validate_provisioning({'runtime_capacity_plan': plan(), 'boot_volume_gb': 38})['required_filesystem_gib'] == 35
