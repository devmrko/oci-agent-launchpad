import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from render_oke import render

CONFIG = {'namespace': 'launchpad-oke', 'service_account': 'service-desk',
          'image': 'icn.ocir.io/example/desk@sha256:' + 'a' * 64,
          'source_build_id': 'function-build-example', 'model_region': 'us-ashburn-1',
          'model_compartment': 'ocid1.compartment.oc1..example', 'model_name': 'example',
          'runtime_secret': 'desk-runtime', 'image_pull_secret': 'ocir-pull',
          'storage_class': 'oci-bv', 'pvc_gib': 50}


def test_storage_identity_and_secret_contract():
    resources = render(CONFIG)
    assert [r['kind'] for r in resources] == ['Namespace', 'ServiceAccount', 'PersistentVolumeClaim', 'Deployment', 'Service']
    deployment = resources[3]['spec']
    assert deployment['replicas'] == 1 and deployment['strategy']['type'] == 'Recreate'
    pod = deployment['template']['spec']
    assert pod['automountServiceAccountToken'] is True
    assert pod['serviceAccountName'] == CONFIG['service_account']
    container = pod['containers'][0]
    env = {e['name']: e for e in container['env']}
    assert env['DESK_OCI_AUTH']['value'] == 'oke'
    assert env['DESK_DATABASE_URL']['value'] == 'sqlite:////data/desk.db'
    assert 'DESK_LANGFUSE_CONFIG' not in env  # projected files are symlinks; app rejects these
    assert env['DESK_LANGFUSE_SECRET_KEY']['valueFrom']['secretKeyRef']['optional'] is False
    assert pod['volumes'][2]['secret']['defaultMode'] == 0o440
    assert container['securityContext']['readOnlyRootFilesystem'] is True
    assert resources[-1]['spec']['type'] == 'ClusterIP'
    assert container['livenessProbe']['tcpSocket']['port'] == 'http'
    assert 'httpGet' not in container['livenessProbe']


@pytest.mark.parametrize('key,value', [('namespace', 'default'), ('namespace', 'kube-system'),
    ('namespace', '../other'), ('image', 'desk:latest'), ('pvc_gib', True), ('pvc_gib', 0),
    ('source_build_id', ''), ('service_account', 'bad/name')])
def test_rejects_unsafe_or_incomplete_input(key, value):
    config = copy.deepcopy(CONFIG)
    config[key] = value
    with pytest.raises(ValueError):
        render(config)


def test_unknown_fields_cannot_inject_plaintext_secrets_or_override_replicas():
    for key in ('password', 'replicas'):
        with pytest.raises(ValueError):
            render({**CONFIG, key: 'unexpected'})
