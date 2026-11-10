"""Render a separate Hello Agent workload; never embed secret values."""
import argparse
import json
import re
from pathlib import Path
import importlib.util

_identity_spec = importlib.util.spec_from_file_location('hello_release_contract', Path(__file__).resolve().parents[1] / 'examples/hello-agent/hello_release.py')
_identity = importlib.util.module_from_spec(_identity_spec)
_identity_spec.loader.exec_module(_identity)


def render(c):
    for key in ("namespace", "service_account", "runtime_secret", "image_pull_secret"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", c[key]):
            raise ValueError("Invalid Kubernetes name")
    if not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}", c["image"]):
        raise ValueError("Digest-pinned image required")
    labels = {"app.kubernetes.io/name": "hello-agent"}
    bootstrap = """import os,json
from pathlib import Path
p=Path('/run/hello')
os.environ['HELLO_TOKEN']=next(iter(json.loads((p/'accounts.json').read_text())))
c={k:(p/f).read_text().strip() for k,f in [('url','lf-url'),('public_key','lf-public'),('secret_key','lf-secret')]}
os.umask(0o077)
Path('/tmp/hello-langfuse.json').write_text(json.dumps(c))
os.environ['HELLO_LANGFUSE_CONFIG']='/tmp/hello-langfuse.json'
os.execvp('python',['python','-m','uvicorn','hello_web:create_app','--factory','--host','0.0.0.0','--port','8092'])
"""
    meta = {"name": "hello-agent", "namespace": c["namespace"], "labels": labels}
    sa = {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": c["service_account"], "namespace": c["namespace"]}}
    container = {"name": "hello-agent", "image": c["image"], "command": ["python", "-c", bootstrap],
        "ports": [{"name": "http", "containerPort": 8092}],
        "env": [{"name": k, "value": v} for k,v in {
            "HELLO_OCI_AUTH":"oke", "HELLO_OCI_REGION":c["model_region"],
            "HELLO_OCI_COMPARTMENT":c["model_compartment"],"HELLO_OCI_MODEL":c["model_name"]}.items()],
        "resources": {"requests": {"cpu":"250m","memory":"256Mi"}, "limits":{"cpu":"1","memory":"768Mi"}},
        "securityContext": {"allowPrivilegeEscalation":False,"readOnlyRootFilesystem":True,"capabilities":{"drop":["ALL"]}},
        "readinessProbe":{"httpGet":{"path":"/health","port":"http"},"initialDelaySeconds":5,"periodSeconds":5},
        "livenessProbe":{"httpGet":{"path":"/health","port":"http"},"initialDelaySeconds":30,"periodSeconds":10},
        "volumeMounts":[{"name":"tmp","mountPath":"/tmp"},{"name":"runtime","mountPath":"/run/hello","readOnly":True}]}
    deployment={"apiVersion":"apps/v1","kind":"Deployment","metadata":meta,"spec":{
        "replicas":1,"progressDeadlineSeconds":600,"selector":{"matchLabels":labels},
        "template":{"metadata":{"labels":labels},"spec":{
            "serviceAccountName":c["service_account"],"automountServiceAccountToken":True,
            "nodeSelector":{"kubernetes.io/arch":"amd64"},
            "imagePullSecrets":[{"name":c["image_pull_secret"]}],
            "securityContext":{"runAsNonRoot":True,"runAsUser":10001,"runAsGroup":10001,"fsGroup":10001,"seccompProfile":{"type":"RuntimeDefault"}},
            "containers":[container],"volumes":[{"name":"tmp","emptyDir":{"sizeLimit":"64Mi"}},
              {"name":"runtime","secret":{"secretName":c["runtime_secret"],"defaultMode":288,
                "items":[{"key":k,"path":v} for k,v in {"demo-accounts.json":"accounts.json","langfuse-url":"lf-url","langfuse-public-key":"lf-public","langfuse-secret-key":"lf-secret"}.items()]}}]}}}}
    service={"apiVersion":"v1","kind":"Service","metadata":meta,"spec":{"type":"ClusterIP","selector":labels,"ports":[{"name":"http","port":8092,"targetPort":"http"}]}}
    if 'release_identity' in c:
        identity = _identity.validate(c['release_identity'])
        container['env'].append({'name':'HELLO_RELEASE_IDENTITY','value':json.dumps(identity,sort_keys=True,separators=(',',':'))})
        deployment['spec']['template']['metadata']['annotations'] = {'launchpad.dev/release-id': identity['release_id']}
    return [sa,deployment,service]

if __name__ == '__main__':
    a=argparse.ArgumentParser();a.add_argument('--config',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    items=render(json.loads(args.config.read_text()));args.output.mkdir(parents=True,exist_ok=False)
    for i,item in enumerate(items): (args.output/f'{i:02d}-{item["kind"].lower()}.json').write_text(json.dumps(item,indent=2)+'\n')
