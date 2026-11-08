"""Render a single-replica OKE workload; never provision or embed secret values."""
import argparse
import json
import re
from pathlib import Path

NAME = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
REQUIRED = {'namespace', 'service_account', 'image', 'source_build_id', 'model_region',
            'model_compartment', 'model_name', 'runtime_secret', 'image_pull_secret',
            'storage_class', 'pvc_gib'}


def render(config):
    if set(config) != REQUIRED:
        raise ValueError('Configuration must contain exactly the documented fields')
    for key in ('namespace', 'service_account', 'runtime_secret', 'image_pull_secret', 'storage_class'):
        if not isinstance(config[key], str) or not re.fullmatch(NAME, config[key]):
            raise ValueError('Invalid Kubernetes name: ' + key)
    if config['namespace'] in {'default', 'kube-system', 'kube-public', 'kube-node-lease'}:
        raise ValueError('Use a dedicated namespace')
    if not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}', config['image']):
        raise ValueError('A digest-pinned image is required')
    for key in ('source_build_id', 'model_region', 'model_compartment', 'model_name'):
        if not isinstance(config[key], str) or not config[key].strip() or '\n' in config[key]:
            raise ValueError('Missing or invalid input: ' + key)
    if type(config['pvc_gib']) is not int or not 1 <= config['pvc_gib'] <= 1024:
        raise ValueError('pvc_gib must be an integer between 1 and 1024')
    ns = config['namespace']
    labels = {'app.kubernetes.io/name': 'service-desk'}
    def obj(api, kind, name, **fields):
        return {'apiVersion': api, 'kind': kind,
                'metadata': {'name': name, 'namespace': ns, 'labels': labels.copy()}, **fields}
    def secret_env(name, key):
        return {'name': name, 'valueFrom': {'secretKeyRef': {
            'name': config['runtime_secret'], 'key': key, 'optional': False}}}
    values = {'DESK_DATABASE_URL': 'sqlite:////data/desk.db', 'DESK_AUTH_MODE': 'demo',
              'DESK_MODEL_BACKEND': 'oci', 'DESK_OCI_AUTH': 'oke',
              'DESK_OCI_REGION': config['model_region'],
              'DESK_OCI_COMPARTMENT': config['model_compartment'],
              'DESK_MODEL_NAME': config['model_name'],
              'DESK_MEMORY_CONFIG': '/run/desk-secrets/memory.json'}
    env = [{'name': k, 'value': v} for k, v in values.items()]
    for name, key in [('DESK_DEMO_ACCOUNTS', 'demo-accounts.json'),
                      ('DESK_LANGFUSE_URL', 'langfuse-url'),
                      ('DESK_LANGFUSE_PUBLIC_KEY', 'langfuse-public-key'),
                      ('DESK_LANGFUSE_SECRET_KEY', 'langfuse-secret-key'),
                      ('DESK_LANGFUSE_CAPTURE_CONTENT', 'langfuse-capture-content')]:
        env.append(secret_env(name, key))
    health = {'httpGet': {'path': '/health', 'port': 'http'}, 'timeoutSeconds': 3}
    pod = {
        'serviceAccountName': config['service_account'], 'automountServiceAccountToken': True,
        'nodeSelector': {'kubernetes.io/os': 'linux', 'kubernetes.io/arch': 'amd64'},
        'imagePullSecrets': [{'name': config['image_pull_secret']}],
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'runAsGroup': 10001,
                            'fsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
        'terminationGracePeriodSeconds': 30,
        'containers': [{'name': 'service-desk', 'image': config['image'], 'imagePullPolicy': 'IfNotPresent',
            'ports': [{'name': 'http', 'containerPort': 8092}], 'env': env,
            'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                                'capabilities': {'drop': ['ALL']}},
            'resources': {'requests': {'cpu': '250m', 'memory': '512Mi', 'ephemeral-storage': '256Mi'},
                          'limits': {'cpu': '1', 'memory': '2Gi', 'ephemeral-storage': '1Gi'}},
            'startupProbe': {**health, 'periodSeconds': 5, 'failureThreshold': 60},
            'readinessProbe': {**health, 'periodSeconds': 5, 'failureThreshold': 3},
            'livenessProbe': {'tcpSocket': {'port': 'http'}, 'timeoutSeconds': 3,
                              'periodSeconds': 15, 'failureThreshold': 3},
            'volumeMounts': [{'name': 'data', 'mountPath': '/data'},
                             {'name': 'tmp', 'mountPath': '/tmp'},
                             {'name': 'runtime', 'mountPath': '/run/desk-secrets', 'readOnly': True}]}],
        'volumes': [{'name': 'data', 'persistentVolumeClaim': {'claimName': 'service-desk-data'}},
                    {'name': 'tmp', 'emptyDir': {'sizeLimit': '256Mi'}},
                    {'name': 'runtime', 'secret': {'secretName': config['runtime_secret'],
                        'defaultMode': 288, 'items': [{'key': 'memory.json', 'path': 'memory.json'}]}}]}
    return [
        {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': ns}},
        obj('v1', 'ServiceAccount', config['service_account']),
        obj('v1', 'PersistentVolumeClaim', 'service-desk-data', spec={
            'accessModes': ['ReadWriteOnce'], 'storageClassName': config['storage_class'],
            'resources': {'requests': {'storage': str(config['pvc_gib']) + 'Gi'}}}),
        obj('apps/v1', 'Deployment', 'service-desk', spec={
            'replicas': 1, 'strategy': {'type': 'Recreate'}, 'progressDeadlineSeconds': 600,
            'selector': {'matchLabels': labels},
            'template': {'metadata': {'labels': labels, 'annotations': {
                'launchpad/source-build-id': config['source_build_id']}}, 'spec': pod}}),
        obj('v1', 'Service', 'service-desk', spec={'type': 'ClusterIP', 'selector': labels,
            'ports': [{'name': 'http', 'port': 8092, 'targetPort': 'http'}]})]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    objects = render(json.loads(args.config.read_text()))
    # JSON documents are valid YAML. Separate artifacts preserve DevOps apply order.
    args.output.mkdir(parents=True, exist_ok=False)
    for index, obj in enumerate(objects):
        (args.output / f'{index:02d}-{obj["kind"].lower()}.json').write_text(json.dumps(obj, indent=2) + '\n')


if __name__ == '__main__':
    main()
