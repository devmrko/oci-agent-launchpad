import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from prepare_pipeline_iam import POLICY, PIPELINE, prepare, statements, check_plan

OWNER = 'ocid1.devopsdeploypipeline.oc1.seoul.owner'
OLD = 'ocid1.devopsdeploypipeline.oc1.seoul.old'
NEW = 'ocid1.devopsdeploypipeline.oc1.seoul.new'


def state(pipeline, policy=False):
    resources = {
        PIPELINE: {'id': pipeline, 'project_id': 'project'},
        'data.oci_devops_project.target': {'id': 'project', 'compartment_id': 'compartment'},
        'data.oci_core_instance.target': {'id': 'vm', 'compartment_id': 'compartment'},
        'oci_devops_deploy_environment.target': {'project_id': 'project', 'compute_instance_group_selectors': [
            {'items': [{'selector_type': 'INSTANCE_IDS', 'compute_instance_ids': ['vm']}]}]}}
    if policy:
        resources[POLICY] = {'id': 'policy', 'compartment_id': 'compartment', 'description': 'original',
                             'statements': statements([OWNER, OLD], 'compartment', 'vm')}
    return {'format_version': '1.0', 'values': {'outputs': {'pipeline_id': {'value': pipeline}},
            'root_module': {'resources': [{'address': key, 'values': value} for key, value in resources.items()]}}}


@pytest.fixture
def inputs(tmp_path):
    return ({'project_id': 'project', 'compartment_id': 'compartment', 'instance_id': 'vm',
             'additional_pipeline_ids': [OLD], 'bundle_path': '/original.zip'},
            state(OWNER, True), state(NEW), tmp_path / 'binding')


def test_additive_inputs(inputs):
    original = copy.deepcopy(inputs[0])
    assert prepare(*inputs)['already_bound'] is False
    value = json.loads((inputs[3] / 'owner.tfvars.json').read_text())
    assert value == {**original, 'additional_pipeline_ids': [OLD, NEW]}
    assert inputs[0] == original


def test_already_bound(inputs):
    inputs[2]['values']['outputs']['pipeline_id']['value'] = OLD
    inputs[2]['values']['root_module']['resources'][0]['values']['id'] = OLD
    assert prepare(*inputs)['already_bound'] is True


def test_stale_input_cannot_drop_old_permissions(inputs):
    inputs[0]['additional_pipeline_ids'] = []
    with pytest.raises(ValueError, match='do not match'):
        prepare(*inputs)
    assert not inputs[3].exists()


@pytest.mark.parametrize('mutation', ['vm', 'project', 'environment', 'policy', 'output'])
def test_wrong_release_is_rejected(inputs, mutation):
    release = inputs[2]
    values = release['values']['root_module']['resources']
    if mutation == 'vm':
        values[2]['values']['id'] = 'other'
    elif mutation == 'project':
        values[0]['values']['project_id'] = 'other'
    elif mutation == 'environment':
        values[3]['values']['compute_instance_group_selectors'][0]['items'][0]['compute_instance_ids'].append('other')
    elif mutation == 'policy':
        values.append({'address': POLICY, 'values': {}})
    else:
        release['values']['outputs']['pipeline_id']['value'] = 'wrong'
    with pytest.raises(ValueError):
        prepare(*inputs)


def plan_for(inputs):
    prepare(*inputs)
    binding = json.loads((inputs[3] / 'binding.json').read_text())
    plan = {'resource_changes': [{'mode': 'managed', 'address': POLICY,
            'change': {'actions': ['update'], 'before': binding['before'], 'after': copy.deepcopy(binding['after']), 'after_unknown': {}}}]}
    return binding, plan


def test_expected_plan(inputs):
    binding, plan = plan_for(inputs)
    assert check_plan(plan, binding)['status'] == 'PLAN_VERIFIED'


@pytest.mark.parametrize('mutation', ['delete', 'replace', 'unknown', 'broader', 'description', 'other', 'drift', 'missing', 'failed_check'])
def test_unexpected_plan_is_rejected(inputs, mutation):
    binding, plan = plan_for(inputs)
    change = plan['resource_changes'][0]['change']
    if mutation == 'delete':
        change['actions'] = ['delete']
    elif mutation == 'replace':
        change['actions'] = ['delete', 'create']
    elif mutation == 'unknown':
        change['after_unknown'] = {'statements': [True]}
    elif mutation == 'broader':
        change['after']['statements'].append('Allow any-user to manage all-resources in tenancy')
    elif mutation == 'description':
        change['after']['description'] = 'changed'
    elif mutation == 'other':
        plan['resource_changes'].append({'mode': 'managed', 'address': PIPELINE, 'change': {'actions': ['update']}})
    elif mutation == 'drift':
        plan['resource_drift'] = [{'change': {'actions': ['update']}}]
    elif mutation == 'failed_check':
        plan['checks'] = [{'status': 'fail'}]
    else:
        plan['resource_changes'] = []
    with pytest.raises(ValueError):
        check_plan(plan, binding)


def test_output_is_never_overwritten(inputs):
    prepare(*inputs)
    with pytest.raises(ValueError, match='exists'):
        prepare(*inputs)


def test_only_computed_policy_etags_can_drift(inputs):
    binding, plan = plan_for(inputs)
    before = copy.deepcopy(binding['before'])
    after = {**before, 'ETag': 'updated', 'lastUpdateETag': 'updated'}
    plan['resource_drift'] = [{'address': POLICY, 'change': {'actions': ['update'], 'before': before, 'after': after}}]
    plan['resource_changes'][0]['change']['before'] = after
    plan['resource_changes'][0]['change']['after']['ETag'] = 'updated'
    assert check_plan(plan, binding)['status'] == 'PLAN_VERIFIED'
    plan['resource_drift'][0]['change']['after']['description'] = 'unexpected'
    with pytest.raises(ValueError, match='drift'):
        check_plan(plan, binding)


def test_consolidation_preserves_exact_permission_principal_pairs():
    import re
    from prepare_pipeline_iam import legacy_statements
    pipelines = [OWNER, OLD, NEW]
    def expand(lines):
        result = set()
        for line in lines:
            prefix, condition = line.split(' where ', 1)
            for principal in re.findall(r"request\.principal\.id = '([^']+)'", condition):
                result.add((prefix, principal))
        return result
    compact = statements(pipelines, 'compartment', 'vm')
    assert len(compact) == 7
    assert expand(compact) == expand(legacy_statements(pipelines, 'compartment', 'vm'))


def test_legacy_policy_can_migrate_without_dropping_principals(inputs):
    from prepare_pipeline_iam import legacy_statements
    for item in inputs[1]['values']['root_module']['resources']:
        if item['address'] == POLICY:
            item['values']['statements'] = legacy_statements([OWNER, OLD], 'compartment', 'vm')
    assert prepare(*inputs)['status'] == 'PREPARED'
