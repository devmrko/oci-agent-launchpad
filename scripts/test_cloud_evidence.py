import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from export_cloud_evidence import entry
from collect_langfuse_evidence import collect

ROOT=Path(__file__).resolve().parents[1]

class CloudEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.record=json.loads((ROOT/'examples/hello-agent/verification/companion-job-2026-11-09.json').read_text())
        self.scope=dict(profile='DEFAULT',tenancy='t',user='u',demo=False,region='ap-seoul-1',compartment='c')
        self.deployment={'data':{'id':self.record['delivery']['deployment_id'],'compartment-id':'c',
                         'lifecycle-state':'SUCCEEDED','deploy-pipeline-id':'ocid1.devopsdeploypipeline.oc1.ap-seoul-1.abc'}}
        tid=self.record['trace']['id']
        self.trace={'project_id':'project1','trace_id':tid,'checked_at':'2026-11-10T01:00:00Z',
                    'observations':[dict(r,trace_id=tid,project_id='project1') for r in self.record['trace']['observations']]}

    def call(self):
        return entry(self.record,self.deployment,self.trace,self.scope,'http://localhost:18080')

    def test_existing_real_record_links_exact_run_and_trace(self):
        result=self.call()
        self.assertIn(self.record['delivery']['deployment_id'],result['stages'][3]['url'])
        self.assertEqual(result['stages'][4]['url'],'http://localhost:18080/project/project1/traces/'+self.trace['trace_id'])
        self.assertIn('미연결',result['stages'][0]['status'])
        self.assertNotIn('answer',json.dumps(result))

    def test_identity_and_success_mismatches_rejected(self):
        changes=[('record',['health','version'],'2'),('record',['chat','mode'],'demo'),
                 ('record',['delivery','job_completed'],False),('record',['checks','model_and_tool'],False),
                 ('record',['trace','id'],'0'*32),('deployment',['data','id'],'other'),
                 ('deployment',['data','compartment-id'],'other'),('deployment',['data','lifecycle-state'],'FAILED'),
                 ('trace',['trace_id'],'0'*32),('trace',['project_id'],'other'),
                 ('trace',['observations'],[]),('trace',['checked_at'],'2025-01-01T00:00:00Z'),
                 ('scope',['region'],'us-ashburn-1'),('scope',['demo'],True)]
        for field,path,value in changes:
            with self.subTest(field=field,path=path):
                original=copy.deepcopy(getattr(self,field)); target=getattr(self,field)
                for key in path[:-1]: target=target[key]
                target[path[-1]]=value
                with self.assertRaises(ValueError): self.call()
                setattr(self,field,original)

    def test_wrong_observation_and_missing_io_rejected(self):
        for key,value in [('trace_id','0'*32),('project_id','other'),('type','SPAN'),('input_present',False)]:
            with self.subTest(key=key):
                original=copy.deepcopy(self.trace)
                self.trace['observations'][0][key]=value
                with self.assertRaises(ValueError): self.call()
                self.trace=original

    def test_collector_wiring_preserves_ids_and_excludes_io(self):
        tid=self.trace['trace_id']
        rows=[dict(traceId=tid,projectId='project1',name=r['name'],type=r['type'],input='PRIVATE INPUT',output='PRIVATE OUTPUT') for r in self.trace['observations']]
        class Response:
            def __init__(self,data): self.data=data
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return json.dumps(self.data).encode()
        with patch('collect_langfuse_evidence.build_opener') as factory:
            client=factory.return_value
            client.open.side_effect=[Response({'data':[{'id':'project1'}]}),Response({'data':rows})]
            result=collect(tid,self.record['observed_at_unix'],'http://127.0.0.1:3000',{'LF_INIT_PUBLIC':'public','LF_INIT_SECRET':'secret'})
            self.assertEqual(len(result['observations']),3)
            self.assertNotIn('PRIVATE',json.dumps(result))
            request=client.open.call_args_list[1].args[0]
            self.assertIn('traceId='+tid,request.full_url)
            self.assertIn('fields=core%2Cbasic%2Cio',request.full_url)
            self.assertEqual(result['observations'][0]['trace_id'],tid)
            for base in ['http://evil.example','http://localhost@evil.example','http://127.0.0.1:3000/?key=x']:
                with self.assertRaises(ValueError): collect(tid,0,base,{})
