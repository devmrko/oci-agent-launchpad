import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from check_spec_links import check
from developer_handoff import prepare, report
from command_evidence import execute
from spec_evidence import execute as unit_execute


class CommandHandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        source = Path(__file__).resolve().parents[1]/'specs/command-evidence/node-example'
        shutil.copytree(source, self.root, dirs_exist_ok=True)

    def prepare(self):
        return prepare(self.root,'specs/cost',['REQ-001'],'음수 검사 구현',['음수 거부, 양수 유지'],self.root/'handoff')

    def test_nonpython_handoff_and_report_without_test_adapter(self):
        baseline = self.prepare()
        self.assertIn('checks.json',baseline['files'])
        self.assertIn('command:checks.json',(self.root/'handoff/TASK.md').read_text())
        evidence = execute(self.root,'checks.json',self.root/'result.json',[sys.executable,'-c','pass'])
        result = report(self.root,baseline,None,self.root/'review',[evidence])
        self.assertEqual(result['status'],'COMMANDS_CURRENT_REVIEW_PENDING')
        self.assertFalse(result['requirements_verified'])

    def test_unittest_runner_refuses_command_tests(self):
        with self.assertRaisesRegex(ValueError,'command_evidence'):
            unit_execute(self.root,'specs/cost',self.root/'result.json')
        self.assertFalse((self.root/'result.json').exists())

    def test_wrong_spec_or_missing_source_rejected(self):
        planpath=self.root/'checks.json'
        plan=json.loads(planpath.read_text())
        plan['files'].remove('cost.cjs')
        planpath.write_text(json.dumps(plan))
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.root/'handoff').exists())

    def test_ambiguous_reference_rejected(self):
        path=self.root/'specs/cost/traceability.json'
        manifest=json.loads(path.read_text())
        manifest['requirements'][0]['tests'][0]['case']='Fake.test_fake'
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            check(self.root,'specs/cost')

    def test_changed_plan_reference_is_flagged(self):
        baseline=self.prepare()
        shutil.copyfile(self.root/'checks.json',self.root/'checks2.json')
        path=self.root/'specs/cost/traceability.json'
        manifest=json.loads(path.read_text())
        manifest['requirements'][0]['tests'][0]['command_plan']='checks2.json'
        path.write_text(json.dumps(manifest))
        evidence=execute(self.root,'checks2.json',self.root/'result.json',[sys.executable,'-c','pass'])
        result=report(self.root,baseline,None,self.root/'review',[evidence])
        self.assertIn('previous_tests_removed_or_reassigned',result['reasons'])
