"""Check selected identity reaches both OCI consumers without fallback."""
import json
import sys
from types import ModuleType
from unittest.mock import Mock

import oci
import pytest

from service_desk.oci_client import inference_client
from service_desk.planning import OciPlanner


@pytest.mark.parametrize('mode', ['instance', 'oke', 'config'])
def test_explicit_identity_selection(monkeypatch, mode):
    instance, workload, config = Mock(return_value=object()), Mock(return_value=object()), Mock(return_value={})
    constructor = Mock()
    monkeypatch.setattr(oci.auth.signers, 'InstancePrincipalsSecurityTokenSigner', instance)
    monkeypatch.setattr(oci.auth.signers, 'get_oke_workload_identity_resource_principal_signer', workload)
    monkeypatch.setattr(oci.config, 'from_file', config)
    monkeypatch.setattr(oci.generative_ai_inference, 'GenerativeAiInferenceClient', constructor)
    inference_client(region='ap-seoul-1', auth=mode)
    assert [instance.call_count, workload.call_count, config.call_count] == {
        'instance': [1, 0, 0], 'oke': [0, 1, 0], 'config': [0, 0, 1]
    }[mode]
    assert constructor.call_args.kwargs['service_endpoint'].endswith('ap-seoul-1.oci.oraclecloud.com')


def test_oke_failure_never_falls_back(monkeypatch):
    workload = Mock(side_effect=RuntimeError('identity unavailable'))
    fallback = Mock()
    monkeypatch.setattr(oci.auth.signers, 'get_oke_workload_identity_resource_principal_signer', workload)
    monkeypatch.setattr(oci.auth.signers, 'InstancePrincipalsSecurityTokenSigner', fallback)
    monkeypatch.setattr(oci.config, 'from_file', fallback)
    with pytest.raises(RuntimeError, match='identity unavailable'):
        inference_client(region='ap-seoul-1', auth='oke')
    fallback.assert_not_called()


def test_unknown_auth_rejected():
    with pytest.raises(ValueError, match='DESK_OCI_AUTH'):
        inference_client(region='ap-seoul-1', auth='automatic')


def test_planner_supplies_selected_identity(monkeypatch):
    factory = Mock()
    monkeypatch.setattr('service_desk.oci_client.inference_client', factory)
    planner = OciPlanner(region='ap-seoul-1', compartment='test', auth='oke')
    factory.assert_called_once_with(region='ap-seoul-1', auth='oke')
    assert planner.client is factory.return_value


def test_memory_supplies_selected_identity(monkeypatch, tmp_path):
    # Stop immediately after the real resources() wiring reaches the factory.
    # No DB credentials, schema creation or remote request is involved.
    from service_desk.memory_backend import resources
    # Optional memory packages are represented only for import; execution stops
    # at the authentication boundary before any of their methods are called.
    for name in ("numpy", "oracledb", "oracleagentmemory", "oracleagentmemory.apis"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    embedders = ModuleType("oracleagentmemory.apis.embedders")
    embedders.IEmbedder = object
    monkeypatch.setitem(sys.modules, embedders.__name__, embedders)
    cfg = tmp_path / 'memory.json'
    cfg.write_text(json.dumps({'embedding_region': 'us-ashburn-1'}))
    monkeypatch.setenv('DESK_MEMORY_CONFIG', str(cfg))
    monkeypatch.setenv('DESK_OCI_AUTH', 'oke')
    factory = Mock(side_effect=RuntimeError('factory reached'))
    monkeypatch.setattr('service_desk.oci_client.inference_client', factory)
    with pytest.raises(RuntimeError, match='factory reached'):
        resources()
    factory.assert_called_once_with(region='us-ashburn-1', auth='oke')
