import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from command_evidence import execute
from build_hello_identity import prepare,contract,ROOT,SPEC,APP_SPEC

class HelloIdentityTests(unittest.TestCase):
    def test_real_command_to_identity_loading_and_stale_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            names=[SPEC,APP_SPEC,'examples/hello-agent/test_release.py','examples/hello-agent/pyproject.toml',
                   *('examples/hello-agent/'+name for name in contract.RUNTIME_FILES)]
            for name in names:
                target=root/name; target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            plan={'schema_version':1,'spec':SPEC,'requirements':['REQ-001'],'files':names}
            (root/'checks.json').write_text(json.dumps(plan))
            evidence=root/'evidence.json'
            execute(root,'checks.json',evidence,[sys.executable,'-c','print("synthetic command fixture")'])
            output=root/'identity.json'
            value=prepare(root,evidence,output)
            self.assertEqual(contract.load(output.read_text(),root/'examples/hello-agent')['release_id'],value['release_id'])
            with self.assertRaises(FileExistsError): prepare(root,evidence,output)
            (root/'examples/hello-agent/agent.py').write_text('# changed')
            with self.assertRaises(ValueError): prepare(root,evidence,root/'new.json')

    def test_renderer_supplies_exact_identity_and_pod_annotation(self):
        spec=importlib.util.spec_from_file_location('identity_renderer',ROOT/'deploy/render_hello_oke.py')
        renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
        files={name:'a'*64 for name in contract.RUNTIME_FILES}
        value={'schema_version':1,'agent_id':'hello-agent','app_version':'0.1.0','runtime_files':files,
               'spec_sha256':'b'*64,'source_sha256':contract.digest(files),'test_evidence_sha256':'c'*64}
        value['release_id']=contract.digest(value)
        config=dict(namespace='demo',service_account='hello',runtime_secret='runtime',image_pull_secret='pull',
                    image='example.test/hello@sha256:'+'d'*64,model_region='example',model_compartment='example',
                    model_name='example',release_identity=value)
        pod=renderer.render(config)[1]['spec']['template']
        env={x['name']:x['value'] for x in pod['spec']['containers'][0]['env']}
        self.assertEqual(json.loads(env['HELLO_RELEASE_IDENTITY']),value)
        self.assertEqual(pod['metadata']['annotations']['launchpad.dev/release-id'],value['release_id'])
        config['release_identity']['release_id']='0'*64
        with self.assertRaises(ValueError): renderer.render(config)
