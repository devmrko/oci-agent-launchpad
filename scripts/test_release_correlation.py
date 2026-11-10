"""Synthetic collection-to-screen wiring and negative identity checks; no cloud calls."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from build_hello_identity import ROOT,SPEC,APP_SPEC,contract,prepare
from command_evidence import execute
from collect_langfuse_evidence import collect,release_metadata
from export_cloud_evidence import entry

class ReleaseCorrelationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        names=[SPEC,APP_SPEC,'examples/hello-agent/test_release.py','examples/hello-agent/pyproject.toml',
               *('examples/hello-agent/'+n for n in contract.RUNTIME_FILES)]
        for name in names:
            dst=self.root/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
        (self.root/'checks.json').write_text(json.dumps({'schema_version':1,'spec':SPEC,'requirements':['REQ-001'],'files':names}))
        evidence=self.root/'evidence.json'
        execute(self.root,'checks.json',evidence,[sys.executable,'-c','print("synthetic fixture")'])
        self.identity=prepare(self.root,evidence,self.root/'identity.json');self.evidence=evidence.read_bytes()
        self.summary={k:self.identity[k] for k in contract.SUMMARY}
        # Copy a historical record only as a test shape; never publish it as new cloud evidence.
        self.record=json.loads((ROOT/'examples/hello-agent/verification/companion-job-2026-11-09.json').read_text())
        self.record['health']['release']=dict(self.summary);self.record['chat']['release']=dict(self.summary)
        self.scope=dict(profile='TEST',tenancy='test',user='test',demo=False,region='ap-seoul-1',compartment='test')
        self.deployment={'data':{'id':self.record['delivery']['deployment_id'],'compartment-id':'test',
                         'lifecycle-state':'SUCCEEDED','deploy-pipeline-id':'ocid1.devopsdeploypipeline.oc1.ap-seoul-1.test'}}
        tid=self.record['trace']['id']
        self.trace={'project_id':'test','trace_id':tid,'checked_at':'2026-11-10T01:00:00Z','observations':[
            dict(r,release=dict(self.summary),trace_id=tid,project_id='test') for r in self.record['trace']['observations']]}

    def render(self):
        return entry(self.record,self.deployment,self.trace,self.scope,'http://localhost:18080',
                     identity=self.identity,evidence=self.evidence,root=self.root)

    def test_collection_to_screen_preserves_only_release_hashes(self):
        tid=self.trace['trace_id']
        rows=[dict(traceId=tid,projectId='test',name=r['name'],type=r['type'],input='PRIVATE BODY',output={},
                   metadata=dict(self.summary,private_token='PRIVATE TOKEN')) for r in self.trace['observations']]
        class Response:
            def __init__(self,data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps(self.data).encode()
        with patch('collect_langfuse_evidence.build_opener') as factory:
            factory.return_value.open.side_effect=[Response({'data':[{'id':'test'}]}),Response({'data':rows})]
            self.trace=collect(tid,self.record['observed_at_unix'],'http://localhost:3000',{'LF_INIT_PUBLIC':'test','LF_INIT_SECRET':'test'})
        self.assertNotIn('PRIVATE',json.dumps(self.trace))
        result=self.render()
        self.assertEqual(result['stages'][0]['status'],'명세·소스·검증 일치')
        self.assertEqual(result['stages'][0]['digest'],self.identity['release_id'])
        self.assertEqual(result['specText'],(self.root/APP_SPEC).read_text())
        self.assertEqual(len(result['stages']),8)
        self.assertEqual(result['stages'][-1]['digest'],self.identity['test_evidence_sha256'])

    def test_each_response_and_observation_mismatch_is_visible(self):
        values=[self.record['health']['release'],self.record['chat']['release'],
                *(r['release'] for r in self.trace['observations'])]
        for value in values:
            for key in contract.SUMMARY:
                with self.subTest(key=key):
                    old=value[key];value[key]='0'*64
                    result=self.render()
                    self.assertEqual(result['stages'][0]['status'],'릴리스 불일치')
                    self.assertEqual(len(result['stages']),5)
                    self.assertNotIn('## REQ-',result['specText'])
                    del value[key]
                    self.assertEqual(self.render()['stages'][0]['status'],'실행 식별 정보 누락')
                    value[key]=old

    def test_changed_sources_and_failed_evidence_require_recheck(self):
        source=self.root/'examples/hello-agent/agent.py';old=source.read_text();source.write_text(old+'\n# changed\n')
        self.assertEqual(self.render()['stages'][0]['status'],'재검증 필요')
        source.write_text(old)
        evidence=json.loads(self.evidence);evidence['status']='COMMAND_FAILED';evidence['exit_code']=1
        self.evidence=json.dumps(evidence).encode()
        self.assertEqual(self.render()['stages'][0]['status'],'재검증 필요')

    def test_invalid_metadata_is_flagged_without_copying_value(self):
        for metadata in ({'release_id':'PRIVATE TOKEN'},'PRIVATE TOKEN'):
            filtered=release_metadata({'metadata':metadata})
            self.assertTrue(filtered['release_invalid']);self.assertNotIn('PRIVATE',json.dumps(filtered))
            self.trace['observations'][0].update(filtered)
            self.assertEqual(self.render()['stages'][0]['status'],'릴리스 자료 오류')

    def test_wrong_evidence_and_missing_arguments_never_link(self):
        self.evidence += b'\n'
        self.assertEqual(self.render()['stages'][0]['status'],'릴리스 불일치')
        self.evidence=None
        self.assertEqual(self.render()['stages'][0]['status'],'대조 자료 누락')
        self.identity=None;self.root=None
        self.assertEqual(self.render()['stages'][0]['status'],'릴리스 근거 미제공')
