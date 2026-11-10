import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'deploy'))
from user_apps import Manager

class ConnectionSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.manager=Manager(self.root/'state');self.addCleanup(self.manager.close)

    def config(self,value):
        path=self.root/'config.json';path.write_text(json.dumps(value));path.chmod(0o600);return path

    def test_private_app_scoped_secrets_resolve_only_at_deploy(self):
        secret=self.root/'secret';secret.write_text('private-value\n');secret.chmod(0o600)
        source=self.config({'env':{'AGENT_PROVIDER':'test'},'secret_files':{'AGENT_API_KEY':str(secret)}})
        response=self.manager.configure('app-one',source)
        self.assertNotIn('private-value',json.dumps(response))
        self.assertNotIn('private-value',(self.root/'state/config/app-one.json').read_text())
        self.assertEqual(self.manager.runtime_env('app-one')['AGENT_API_KEY'],'private-value')
        self.assertEqual(self.manager.runtime_env('app-two'),{})
        secret.write_text('rotated');self.assertEqual(self.manager.runtime_env('app-one')['AGENT_API_KEY'],'rotated')
        secret.chmod(0o644)
        with self.assertRaises(ValueError):self.manager.runtime_env('app-one')

    def test_unsafe_settings_refused(self):
        for key in ['PATH','HOME','PYTHONPATH','LD_PRELOAD','JAVA_TOOL_OPTIONS','PORT']:
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.manager.configure('app-one',self.config({'env':{key:'x'},'secret_files':{}}))
        source=self.config({'env':{},'secret_files':{}});source.chmod(0o644)
        with self.assertRaises(ValueError):self.manager.configure('app-one',source)

    def test_settings_never_reach_build_or_other_apps(self):
        source=self.root/'source';source.mkdir()
        (source/'app.py').write_text('print("unused")')
        manifest={'schema_version':1,'id':'env-check','version':'v1','files':['app.py'],
                  'build':[[sys.executable,'-c','import os; assert "AGENT_API_KEY" not in os.environ']],
                  'run':[sys.executable,'app.py'],'health_path':'/ready'}
        (source/'app.json').write_text(json.dumps(manifest))
        self.manager.configure('env-check',self.config({'env':{'AGENT_API_KEY':'private-value'},'secret_files':{}}))
        self.manager.register(source)
        self.assertNotIn('private-value',json.dumps(self.manager.status()))
        self.assertNotIn('private-value',self.manager.logs('env-check','v1','build')['tail'])

if __name__=='__main__':unittest.main()
