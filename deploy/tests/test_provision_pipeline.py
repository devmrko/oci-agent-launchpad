import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
import provision_pipeline as provision
from test_prepare_release import inputs, call
from test_verify_release import result


def plan():
    return {'resource_changes': [{'mode': 'managed', 'address': address, 'change': {'actions': ['create']}}
                                  for address in provision.ADDRESSES]}


@pytest.mark.parametrize('mutation', ['delete', 'update', 'replace', 'extra', 'missing', 'reused', 'drift', 'failed'])
def test_unsafe_release_plans_rejected(mutation):
    value = plan()
    change = value['resource_changes'][0]['change']
    if mutation in ('delete', 'update'):
        change['actions'] = [mutation]
    elif mutation == 'replace':
        change['actions'] = ['delete', 'create']
    elif mutation == 'extra':
        value['resource_changes'].append({'mode': 'managed', 'address': 'unexpected', 'change': {'actions': ['create']}})
    elif mutation == 'missing':
        value['resource_changes'].pop()
    elif mutation == 'drift':
        value['resource_drift'] = [{'change': {'actions': ['update']}}]
    elif mutation == 'failed':
        value['checks'] = [{'status': 'fail'}]
    with pytest.raises(ValueError):
        provision.release_plan(value, mutation == 'reused')


def test_new_release_plan_allows_deferred_upload_conditions():
    value = plan(); value['checks'] = [{'status': 'unknown'}]
    provision.release_plan(value, False)


@pytest.fixture
def prepared(result, inputs, tmp_path):
    out = tmp_path / 'prepared'
    call(result, inputs, out)
    sha = hashlib.sha256((out / 'preparation.json').read_bytes()).hexdigest()
    return out, sha, inputs


def test_validated_inputs_and_tamper(prepared):
    out, sha, _ = prepared
    provision.prepared_inputs(out, sha)
    with (out / 'result/release.zip').open('ab') as stream:
        stream.write(b'tampered')
    with pytest.raises(ValueError):
        provision.prepared_inputs(out, sha)


@pytest.mark.parametrize('execute,iam_only,fail', [(False, False, False), (True, False, False),
                                                   (True, False, True), (True, True, False)])
def test_orchestration_stops_or_resumes_at_correct_stage(prepared, tmp_path, monkeypatch, execute, iam_only, fail):
    out, sha, inputs = prepared
    base = json.loads(inputs[0].read_text())
    args = SimpleNamespace(prepared=out, receipt_sha256=sha, owner_vars=inputs[0], output=tmp_path/'run',
                           release_workspace='new', owner_workspace='owner', terraform=Path('/terraform'),
                           module=Path('/module'), execute=execute, iam_only=iam_only)
    target = tuple(base[k] for k in ('project_id', 'compartment_id', 'instance_id'))
    monkeypatch.setattr(provision, 'identity', lambda value: ('pipeline', target))
    monkeypatch.setattr(provision, 'check_plan', lambda *args: None)
    monkeypatch.setattr(provision, 'prepare', lambda a,b,c,d: (d.mkdir(), (d/'binding.json').write_text('{}')))
    events = []
    class Fake:
        def __init__(self, executable, module, workspace, output):
            self.workspace=workspace
        def state(self):
            return {'values': {'outputs': {'bootstrap_release': {'value': {
                'directory':'new', 'version':'0.4.2',
                'manifest_sha256': json.loads((out/'preparation.json').read_text())['manifest_sha256']}}}}}
        def plan(self, variables, name):
            events.append('plan-'+name)
            if fail and name == 'iam':
                raise RuntimeError('iam unavailable')
            return plan(), Path(name)
        def apply(self, saved):
            events.append('apply-'+str(saved))
    if fail:
        with pytest.raises(RuntimeError):
            provision.run(args, Fake)
        assert events == ['plan-release', 'apply-release', 'plan-iam']
        assert json.loads((args.output/'progress.json').read_text())['failed_stage'] == 'PLANNING_IAM'
    else:
        status=provision.run(args, Fake)
        expected=['plan-iam', 'apply-iam'] if iam_only else (['plan-release', 'apply-release', 'plan-iam', 'apply-iam'] if execute else ['plan-release'])
        assert events == expected
        assert status['stage'] == ('INFRASTRUCTURE_APPLIED' if execute else 'RELEASE_PLAN_VERIFIED')


def test_terraform_environment_and_json_logs_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv('TF_CLI_ARGS_plan', '-destroy')
    monkeypatch.setenv('TF_VAR_instance_id', 'unexpected')
    captured = {}
    def execute(command, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=b'{"private_state":"do not log"}', stderr=b'')
    monkeypatch.setattr(provision.subprocess, 'run', execute)
    tf = provision.Terraform(Path('/tf'), Path('/module'), 'release', tmp_path)
    assert tf.call('show', '-json').startswith(b'{')
    assert 'TF_CLI_ARGS_plan' not in captured['env']
    assert 'TF_VAR_instance_id' not in captured['env']
    assert captured['env']['TF_WORKSPACE'] == 'release'
    assert 'private_state' not in (tmp_path/'terraform.log').read_text()
