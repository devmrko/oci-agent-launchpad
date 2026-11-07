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
