import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('user_apps',ROOT/'deploy/user_apps.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class UserAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'source'
        shutil.copytree(ROOT/'examples/bring-your-agent/python',self.source)
        self.manager=m.Manager(self.root/'state');self.addCleanup(self.manager.close)

    def test_register_is_snapshot_and_refuses_duplicate_or_tamper(self):
        self.manager.register(self.source)
        self.assertEqual(self.manager.status('user-python')['versions'],['v1'])
        with self.assertRaises(ValueError):self.manager.register(self.source)
        (self.source/'app.py').write_text('# source changed; registered copy unchanged')
        stored=self.manager.release('user-python','v1')/'app.py'
        self.assertIn('HTTPServer',stored.read_text())
        stored.write_text('# artifact changed')
        with self.assertRaises(ValueError):self.manager.deploy('user-python','v1')

    def test_invalid_source_and_shell_string_rejected(self):
        original=json.loads((self.source/'app.json').read_text())
        for key,value in [('id','../escape'),('version','../escape'),('files',['../key']),('files',['.env']),('files',['release.json']),('run','python3 app.py'),('health_path','http://evil.test')]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):m.manifest(dict(original,**{key:value}))

    def test_symlink_is_not_copied(self):
        path=self.source/'app.py';path.unlink();path.symlink_to(ROOT/'examples/bring-your-agent/python/app.py')
        with self.assertRaises(ValueError):self.manager.register(self.source)
        self.assertFalse(self.manager.release('user-python','v1').exists())

    def test_runtime_failure_keeps_healthy_process(self):
        self.manager.register(self.source);before=self.manager.deploy('user-python','v1')
        config=json.loads((self.source/'app.json').read_text());config.update(version='bad',run=['python3','missing.py','{port}'])
        (self.source/'app.json').write_text(json.dumps(config));self.manager.register(self.source)
        with self.assertRaises(ValueError):self.manager.deploy('user-python','bad')
        after=self.manager.status('user-python')
        self.assertEqual((before['pid'],before['port']),(after['pid'],after['port']))
        self.assertEqual(after['status'],'UP')
        self.assertIn('started v1',self.manager.logs('user-python','v1')['tail'])
        self.manager.stop('user-python');self.assertEqual(self.manager.status('user-python')['status'],'STOPPED')

if __name__=='__main__':unittest.main()
