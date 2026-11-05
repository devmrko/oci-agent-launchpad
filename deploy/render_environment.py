"""Render environment bindings without executing cloud/SSH or reading secret values."""
import argparse
import json
import os
import re
from pathlib import Path


def render(config, outputs):
    required = ['name','profile','region','compartment_id','tenancy_id','user_id','model_region',
                'chat_model','embedding_model','memory_store_id','memory_schema_owner',
                'memory_runtime_user','memory_namespace','memory_config_path','companion_token_file']
    for key in required:
        value=config.get(key)
        if not isinstance(value,str) or not value or any(c in value for c in '\n\r\x00'):
            raise ValueError('Missing or invalid setting: '+key)
    for key in ['name','profile','region','model_region','chat_model','embedding_model','memory_namespace']:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',config[key]):raise ValueError('Invalid setting: '+key)
    for key in ['memory_schema_owner','memory_runtime_user','memory_store_id']:
        cap=16 if key=='memory_store_id' else 30
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,'+str(cap-1)+'}',config[key]):raise ValueError('Invalid SQL identifier: '+key)
    for key in ['compartment_id','tenancy_id','user_id']:
        if not re.fullmatch(r'ocid1\.[A-Za-z0-9_.-]+',config[key]):raise ValueError('Invalid OCID: '+key)
    if config['memory_schema_owner']==config['memory_runtime_user']:raise ValueError('Separate database users required')
    port=config.get('companion_tunnel_port',8093)
    dimensions=config.get('embedding_dimensions',1536)
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('Invalid tunnel port')
    if type(dimensions) is not int or not 1<=dimensions<=65536:raise ValueError('Invalid dimensions')
    for key in ['memory_config_path','companion_token_file']:
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+',config[key]):raise ValueError('Use absolute safe path: '+key)
    binding=outputs['deployment']['value']
    for key in ['region','compartment_id']:
        if binding[key]!=config[key]:raise ValueError('Terraform/environment mismatch: '+key)
    env={'DESK_MODEL_BACKEND':'oci','DESK_OCI_AUTH':'instance','DESK_OCI_REGION':config['model_region'],
         'DESK_OCI_COMPARTMENT':config['compartment_id'],'DESK_MODEL_NAME':config['chat_model'],
         'DESK_MEMORY_CONFIG':config['memory_config_path']}
    if binding.get('memory_adb_id') is None:
        env.pop('DESK_MEMORY_CONFIG')
    memory={'compartment':config['compartment_id'],'embedding_region':config['model_region'],
            'embedding_model':config['embedding_model'],'embedding_dimensions':dimensions,
            'store_id':config['memory_store_id'],'schema_owner':config['memory_schema_owner'],
            'user':config['memory_runtime_user'],'namespace':config['memory_namespace']}
    companion={'name':config['name'],'profile':config['profile'],'tenancy':config['tenancy_id'],
               'user':config['user_id'],'region':config['region'],'compartment':config['compartment_id'],
               'baseUrl':f'http://127.0.0.1:{port}','tokenFile':config['companion_token_file']}
    return {'model.env':'\n'.join(k+'='+v for k,v in env.items())+'\n',
            'memory-settings.json':json.dumps(memory,indent=2),
            'agent-monitor.json':json.dumps(companion,indent=2),
            'deployment-target.json':json.dumps(binding,indent=2)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--environment',required=True);p.add_argument('--terraform-output',required=True);p.add_argument('--output-dir',required=True)
    a=p.parse_args();files=render(json.loads(Path(a.environment).read_text()),json.loads(Path(a.terraform_output).read_text()))
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    for name,text in files.items():
        with os.fdopen(os.open(out/name,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:f.write(text)
    print('Rendered four configuration files; no cloud changes or secret reads.')

if __name__=='__main__':main()
