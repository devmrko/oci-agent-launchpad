import importlib.util
from pathlib import Path
import pytest
spec = importlib.util.spec_from_file_location('oke_secret', Path(__file__).parents[1] / 'sync_oke_secret.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_exact_runtime_fields_and_no_last_applied_plaintext():
    p = {'type': 'Opaque', 'data': {k: 'test-value' for k in m.RUNTIME_KEYS}}
    d = m.secret_document(p, 'test-oke', 'runtime', 'vault-ref', 7)
    assert set(d['data']) == m.RUNTIME_KEYS
    assert d['metadata']['annotations']['launchpad/vault-version'] == '7'
    assert 'test-value' not in str(d)

@pytest.mark.parametrize('ns', ['default', 'kube-system', 'bad/name'])
def test_reject_system_or_invalid_namespace(ns):
    with pytest.raises(ValueError):
        m.secret_document({'type':'kubernetes.io/dockerconfigjson','data':{'.dockerconfigjson':'{}'}}, ns, 'pull', 'vault', 1)

def test_reject_extra_secret_field():
    p = {'type':'Opaque', 'data':{k:'value' for k in m.RUNTIME_KEYS}}
    p['data']['admin-password'] = 'must-not-copy'
    with pytest.raises(ValueError): m.secret_document(p,'test-oke','runtime','vault',1)
