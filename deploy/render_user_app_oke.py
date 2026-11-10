"""Render generic user-app OKE resources; no cloud changes or application dependencies."""
import argparse
import json
from pathlib import Path
import re
from user_apps import manifest,check


def render(app,target):
    app=manifest(app)
    if set(target)!={'namespace','image','port','working_directory'}:raise ValueError('Expected namespace, image, port and working_directory')
    ns=check(target['namespace']);name=app['id'];port=target['port'];image=target['image']
    if ns in {'default','kube-system','kube-public','kube-node-lease'}:raise ValueError('Dedicated namespace required')
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('Invalid port')
    if not isinstance(image,str) or not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}',image):raise ValueError('Digest-pinned image required')
    directory=target['working_directory']
    if not isinstance(directory,str) or not re.fullmatch(r'/[A-Za-z0-9_/-]*',directory) or '..' in Path(directory).parts:raise ValueError('Invalid container working directory')
    labels={'app.kubernetes.io/name':name}
    def obj(kind,api='v1',**fields):return dict(apiVersion=api,kind=kind,metadata={'name':name,'namespace':ns,'labels':labels},**fields)
    container={'name':name,'image':image,'workingDir':directory,'command':[v.replace('{port}',str(port)) for v in app['run']],
               'env':[{'name':'PORT','value':str(port)},{'name':'APP_VERSION','value':app['version']},{'name':'BIND_HOST','value':'0.0.0.0'},{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}],
               'ports':[{'name':'http','containerPort':port}],
               'readinessProbe':{'httpGet':{'path':app['health_path'],'port':'http'},'timeoutSeconds':2,'periodSeconds':5},
               'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}},
               'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
               'volumeMounts':[{'name':'tmp','mountPath':'/tmp'}]}
    deployment=obj('Deployment','apps/v1',spec={'replicas':1,'selector':{'matchLabels':labels},'progressDeadlineSeconds':120,
        'template':{'metadata':{'labels':labels,'annotations':{'launchpad.dev/app-version':app['version']}},'spec':{
          'serviceAccountName':name,'automountServiceAccountToken':False,
          'securityContext':{'runAsNonRoot':True,'runAsUser':10001,'runAsGroup':10001,'seccompProfile':{'type':'RuntimeDefault'}},
          'containers':[container],'volumes':[{'name':'tmp','emptyDir':{'sizeLimit':'64Mi'}}]}}})
    return [obj('ServiceAccount'),deployment,obj('Service',spec={'type':'ClusterIP','selector':labels,'ports':[{'port':port,'targetPort':'http'}]})]

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--target',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();objects=render(json.loads(a.manifest.read_text()),json.loads(a.target.read_text()));a.output.mkdir(parents=True,exist_ok=False)
    for index,item in enumerate(objects):(a.output/f'{index:02d}-{item["kind"].lower()}.json').write_text(json.dumps(item,indent=2)+'\n')
    print(json.dumps({'status':'RENDERED','resources':len(objects),'cloud_deployed':False}))
