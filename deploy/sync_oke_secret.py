"""Copy a versioned OCI Vault payload to one namespace-scoped Kubernetes Secret."""
import argparse
import base64
import json
import re
import subprocess

RUNTIME_KEYS = {'memory.json', 'demo-accounts.json', 'langfuse-url', 'langfuse-public-key', 'langfuse-secret-key', 'langfuse-capture-content'}

def secret_document(payload, namespace, name, source_id, version):
    for value in (namespace, name):
        if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', value):
            raise ValueError('Invalid namespace or secret name')
    if namespace in {'default', 'kube-system', 'kube-public', 'kube-node-lease'}:
        raise ValueError('Dedicated namespace required')
    if set(payload) != {'type', 'data'} or not isinstance(payload['data'], dict):
        raise ValueError('Invalid Vault envelope')
    kind, data = payload['type'], payload['data']
    keys = RUNTIME_KEYS if kind == 'Opaque' else {'.dockerconfigjson'} if kind == 'kubernetes.io/dockerconfigjson' else None
    if keys is None or set(data) != keys or any(not isinstance(v, str) or not v for v in data.values()):
        raise ValueError('Invalid secret fields')
    if len(json.dumps(data).encode()) > 500_000:
        raise ValueError('Secret too large')
    return {'apiVersion': 'v1', 'kind': 'Secret', 'type': kind,
            'metadata': {'name': name, 'namespace': namespace,
                         'annotations': {'launchpad/vault-secret-id': source_id, 'launchpad/vault-version': str(version)}},
            'data': {key: base64.b64encode(value.encode()).decode() for key, value in data.items()}}

def main():
    import oci
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('secret-id', 'namespace', 'name', 'region', 'kubeconfig', 'kubectl', 'server', 'tls-server-name'):
        p.add_argument('--'+arg, required=True)
    p.add_argument('--version', type=int, required=True)
    a = p.parse_args()
    cfg = oci.config.from_file(); cfg['region'] = a.region
    try:
        bundle = oci.secrets.SecretsClient(cfg).get_secret_bundle(a.secret_id, version_number=a.version).data
        payload = json.loads(base64.b64decode(bundle.secret_bundle_content.content, validate=True))
        document = secret_document(payload, a.namespace, a.name, a.secret_id, bundle.version_number)
        command = [a.kubectl, '--kubeconfig', a.kubeconfig, '--server', a.server,
                   '--tls-server-name', a.tls_server_name, 'apply', '--server-side',
                   '--field-manager=launchpad-vault-sync', '-f', '-']
        result = subprocess.run(command, input=json.dumps(document).encode(), capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError('Kubernetes Secret apply failed; response suppressed to protect values')
    except Exception as error:
        raise SystemExit('Secret sync failed: '+type(error).__name__) from None
    print(json.dumps({'secret': a.name, 'namespace': a.namespace, 'vault_version': bundle.version_number, 'status': 'APPLIED'}))

if __name__ == '__main__':
    main()
