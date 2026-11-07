from contextlib import nullcontext
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]))
import run_deployment_check as verifier


@pytest.fixture
def configured(tmp_path,monkeypatch):
    release=tmp_path/'releases/r1/venv/bin';release.mkdir(parents=True)
    (release/'python').write_text('placeholder')
    script=tmp_path/'check_deployment.py';script.write_text('placeholder')
    (tmp_path/'check_runtime.py').write_text('placeholder')
    config={'allowed_releases':['r1'],'credentials_file':str(tmp_path/'credentials.json'),'timeout_seconds':120}
    deployment={'service':'demo','release_root':str(tmp_path/'releases'),'port':8092,'releases':{'r1':{'directory':'r1','version':'0.5.0'},'r2':{'directory':'r2','version':'0.5.1'}}}
    for name,value in [('config.json',config),('deployment.json',deployment),('credentials.json',{'token':'SECRET'})]:
        p=tmp_path/name;p.write_text(json.dumps(value));p.chmod(0o600)
    monkeypatch.setattr(verifier,'trusted',lambda p:None)
    monkeypatch.setattr(verifier,'deployment_lock',lambda p:nullcontext())
    return tmp_path,script,release/'python',config,deployment


def test_active_release_receives_credentials_only_on_stdin(configured,monkeypatch):
    root,script,python,config,deployment=configured
    calls=[]
    def invoke(command,**kwargs):
        calls.append((command,kwargs))
        if len(calls)==1:return SimpleNamespace(stdout='{ path='+str(python)+' ; argv[]=ignored }',returncode=0)
        assert 'SECRET' not in ' '.join(command)
        assert json.loads(kwargs['input'])['token']=='SECRET'
        assert kwargs['env']=={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
        assert command[1:3]==['-E','-s']
        return SimpleNamespace(returncode=0,stdout=json.dumps({'result':'PASS','version':'0.5.0','untrusted_extra':'SECRET','telemetry':{'chat_input_output':True,'memory_content_excluded':True,'observations':5}}))
    monkeypatch.setattr(verifier.subprocess,'run',invoke)
    result=verifier.run('r1',root/'config.json',root/'deployment.json',script,root/'lock')
    assert result['result']=='PASS' and 'SECRET' not in json.dumps(result)
    assert len(calls)==2


def test_inactive_release_cannot_read_credentials(configured,monkeypatch):
    root,script,_,_,_=configured
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout='{ path=/other/python ; }'))
    (root/'credentials.json').unlink()
    with pytest.raises(ValueError,match='not active'):verifier.run('r1',root/'config.json',root/'deployment.json',script,root/'lock')


def test_unlisted_alias_denied_before_execution(configured,monkeypatch):
    root,script,*_=configured
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**k:pytest.fail('must not execute'))
    with pytest.raises(ValueError,match='not allowed'):verifier.run('r2',root/'config.json',root/'deployment.json',script,root/'lock')


def test_sudoers_has_exact_alias_without_wildcards(configured):
    *_,config,deployment=configured
    assert verifier.sudoers(config,deployment)=='ocarun ALL=(root) NOPASSWD: /usr/local/sbin/launchpad-check r1\n'


def test_credentials_permissions(configured):
    root,*_=configured
    p=root/'credentials.json';p.chmod(0o644)
    with pytest.raises(ValueError,match='private'):verifier.private_json(p)


@pytest.mark.parametrize('outcome',['failure','timeout','invalid-json'])
def test_child_failure_is_never_success(configured,monkeypatch,outcome):
    root,script,python,*_=configured
    def invoke(command,**kwargs):
        if command[0]=='/usr/bin/systemctl':return SimpleNamespace(stdout='{ path='+str(python)+' ; }')
        if outcome=='timeout':raise verifier.subprocess.TimeoutExpired(command,120)
        return SimpleNamespace(returncode=1 if outcome=='failure' else 0,stdout='SECRET invalid')
    monkeypatch.setattr(verifier.subprocess,'run',invoke)
    with pytest.raises((RuntimeError,ValueError,verifier.subprocess.TimeoutExpired)):
        verifier.run('r1',root/'config.json',root/'deployment.json',script,root/'lock')
