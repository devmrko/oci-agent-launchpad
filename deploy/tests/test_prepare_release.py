import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from prepare_release import prepare
from test_verify_release import result

@pytest.fixture
def inputs(tmp_path):
    base={'region':'ap-seoul-1','home_region':'us-ashburn-1','compartment_id':'ocid1.compartment.oc1..test',
          'project_id':'ocid1.devopsproject.oc1.test','instance_id':'ocid1.instance.oc1.test','create_deployment_policy':False}
    config={'service':'demo','release_root':'/opt/releases','staging_root':'/var/ocarun_staging/launchpad','port':8092,
            'releases':{'old':{'directory':'old','version':'0.4.1','manifest_sha256':'d'*64}}}
    bp=tmp_path/'base.json';cp=tmp_path/'config.json'
    bp.write_text(json.dumps(base));cp.write_text(json.dumps(config))
    return bp,cp


def call(result, inputs, out, **kwargs):
    return prepare(result,*inputs,out,kwargs.pop('expected_build','test-build'),
                   kwargs.pop('expected_app','b'*40),'a'*40,kwargs.pop('alias','new'))


def test_outputs_share_verified_identity_and_preserve_previous_releases(result,inputs,tmp_path):
    original=inputs[1].read_bytes();out=tmp_path/'prepared'
    receipt=call(result,inputs,out)
    config=json.loads((out/'deployment.json').read_text());variables=json.loads((out/'release.tfvars.json').read_text())
    assert config['releases']['old']==json.loads(original)['releases']['old']
    assert config['releases']['new']['manifest_sha256']==variables['manifest_sha256']==receipt['manifest_sha256']
    assert variables['app_version']=='0.4.2' and variables['create_deployment_policy'] is False
    assert Path(variables['bundle_path']).read_bytes()==(result/'release.zip').read_bytes()
    assert inputs[1].read_bytes()==original and receipt['status']=='READY'
    with pytest.raises(ValueError,match='already exists'):call(result,inputs,out)

@pytest.mark.parametrize('kwargs',[{'expected_build':'other'},{'expected_app':'c'*40}])
def test_wrong_build_provenance_produces_no_output(result,inputs,tmp_path,kwargs):
    out=tmp_path/'out'
    with pytest.raises(ValueError,match='provenance'):call(result,inputs,out,**kwargs)
    assert not out.exists()


def test_changed_existing_alias_is_not_overwritten(result,inputs,tmp_path):
    with pytest.raises(ValueError,match='different contents'):call(result,inputs,tmp_path/'out',alias='old')
    assert not (tmp_path/'out').exists()


def test_identical_existing_alias_is_reusable(result,inputs,tmp_path):
    first=tmp_path/'first';call(result,inputs,first)
    receipt=call(result,(inputs[0],first/'deployment.json'),tmp_path/'second')
    assert receipt['existing_alias_reused'] is True
    assert (first/'deployment.json').read_bytes()==(tmp_path/'second'/'deployment.json').read_bytes()

@pytest.mark.parametrize('change,message',[
    ({'password':'never-copy'},'Unknown'),
    ({'staging_root':'/wrong'},'staging'),
    ({'additional_pipeline_ids':['ocid1.devopsdeploypipeline.oc1.old']},'policy owner'),
    ({'instance_id':'ocid1.compartment.oc1.wrong'},'identifier'),
])
def test_unsafe_or_conflicting_inputs_rejected(result,inputs,tmp_path,change,message):
    base=json.loads(inputs[0].read_text());base.update(change);inputs[0].write_text(json.dumps(base))
    with pytest.raises(ValueError,match=message):call(result,inputs,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_alias_cannot_reuse_another_release_directory(result,inputs,tmp_path):
    cfg=json.loads(inputs[1].read_text());cfg['releases']['old']['directory']='new';inputs[1].write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='directory belongs'):call(result,inputs,tmp_path/'out')


def test_copy_failure_has_no_ready_marker(result,inputs,tmp_path,monkeypatch):
    import prepare_release
    def fail(*args):raise OSError('disk full')
    monkeypatch.setattr(prepare_release.shutil,'copyfile',fail)
    out=tmp_path/'out'
    with pytest.raises(OSError):call(result,inputs,out)
    assert out.exists() and not (out/'preparation.json').exists()


def test_tampered_build_creates_no_output(result,inputs,tmp_path):
    with (result/'release.zip').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='checksum'):call(result,inputs,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_optional_verifier_survives_preparation(result, inputs, tmp_path):
    base=json.loads(inputs[0].read_text())
    base.update(post_deploy_check_command='/usr/local/sbin/launchpad-check',post_deploy_check_timeout_seconds=120)
    inputs[0].write_text(json.dumps(base))
    out=tmp_path/'prepared';call(result,inputs,out)
    actual=json.loads((out/'release.tfvars.json').read_text())
    assert actual['post_deploy_check_command']==base['post_deploy_check_command']
    assert actual['post_deploy_check_timeout_seconds']==120


@pytest.mark.parametrize('field,value', [('post_deploy_check_command','/usr/local/sbin/check;id'),
    ('post_deploy_check_command','/tmp/check'),('post_deploy_check_timeout_seconds',True),
    ('post_deploy_check_timeout_seconds',601)])
def test_invalid_verifier_fails_before_output(result, inputs, tmp_path, field, value):
    base=json.loads(inputs[0].read_text());base[field]=value;inputs[0].write_text(json.dumps(base))
    out=tmp_path/'prepared'
    with pytest.raises(ValueError,match='verifier'):call(result,inputs,out)
    assert not out.exists()
