import json
from pathlib import Path
import tempfile
import unittest

from export_companion_evidence import export
from local_release_demo import demo


class ExportEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.directory=Path(cls.temp.name)/'releases'
        demo(Path(__file__).resolve().parents[1],cls.directory)
        cls.scope=dict(profile='DEMO',tenancy='t',user='u',demo=True,region='r',compartment='c')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_verified_snapshots_do_not_claim_cloud_or_trace(self):
        result=export(self.directory,self.scope,'http://example.test',Path(self.temp.name)/'export.json')
        self.assertEqual(len(result['entries']),2)
        for entry in result['entries']:
            self.assertEqual(entry['scope'],self.scope)
            self.assertIn('OCI 미배포',entry['stages'][3]['status'])
            self.assertIn('미연결',entry['stages'][4]['status'])
            self.assertEqual(len(entry['stages'][2]['digest']),64)
        with self.assertRaises(FileExistsError):
            export(self.directory,self.scope,'http://example.test',Path(self.temp.name)/'export.json')

    def test_archive_record_mismatch_rejected(self):
        path=self.directory/'summary.json'; original=path.read_text()
        try:
            data=json.loads(original);data['releases']['a']['archive_sha256']='0'*64
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                export(self.directory,self.scope,'http://example.test',Path(self.temp.name)/'bad.json')
        finally: path.write_text(original)

    def test_unsafe_link_rejected(self):
        for url in ['javascript:alert(1)','https://user:pass@example.test','https://example.test/?token=x']:
            with self.assertRaises(ValueError):
                export(self.directory,self.scope,url,Path(self.temp.name)/'unsafe.json')
