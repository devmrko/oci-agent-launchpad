import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('render_environment',ROOT/'render_environment.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((ROOT/'environment.example.json').read_text())
        for k in ['compartment_id','tenancy_id','user_id']:self.cfg[k]='ocid1.'+k+'.test'
        self.out={'deployment':{'value':{'region':self.cfg['region'],'compartment_id':self.cfg['compartment_id'],'instance_id':'test','public_ip':'192.0.2.2','memory_adb_id':'test'}}}
    def test_bindings_and_no_password(self):
        result=module.render(self.cfg,self.out)
        self.assertEqual(json.loads(result['memory-settings.json'])['schema_owner'],'LP_MEMORY_OWNER')
        self.assertEqual(json.loads(result['agent-monitor.json'])['baseUrl'],'http://127.0.0.1:8093')
        self.assertNotIn('password',str(result))
    def test_without_adb_does_not_enable_memory(self):
        self.out['deployment']['value']['memory_adb_id']=None
        self.assertNotIn('DESK_MEMORY_CONFIG=',module.render(self.cfg,self.out)['model.env'])
    def test_mismatched_scope_rejected(self):
        self.out['deployment']['value']['region']='different-region'
        with self.assertRaises(ValueError):module.render(self.cfg,self.out)
    def test_sql_and_env_injection_rejected(self):
        for field,value in [('memory_schema_owner','OWNER;DROP'),('chat_model','model\nINJECT=x'),('compartment_id','bad" value')]:
            with self.subTest(field=field),self.assertRaises(ValueError):module.render({**self.cfg,field:value},self.out)
    def test_separate_schema_accounts_required(self):
        with self.assertRaises(ValueError):module.render({**self.cfg,'memory_runtime_user':'LP_MEMORY_OWNER'},self.out)

if __name__=='__main__':unittest.main()
