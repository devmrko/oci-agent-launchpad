import json
from pathlib import Path
import sys
import tempfile
import unittest

from command_evidence import execute, inspect, snapshot


class CommandEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root/'spec.md').write_text('## REQ-001 Example\n')
        (self.root/'app.txt').write_text('original')
        self.plan = {'schema_version': 1, 'spec': 'spec.md', 'requirements': ['REQ-001'], 'files': ['app.txt']}
        self.save_plan()

    def save_plan(self):
        (self.root/'plan.json').write_text(json.dumps(self.plan))

    def run_command(self, code, timeout=3):
        return execute(self.root, 'plan.json', self.root/'result.json', [sys.executable, '-S', '-c', code], timeout)

    def test_success_is_not_requirement_verification(self):
        result = self.run_command("from pathlib import Path; assert Path('app.txt').read_text() == 'original'")
        self.assertEqual(result['status'], 'COMMAND_SUCCEEDED')
        self.assertFalse(result['requirements_verified'])
        self.assertTrue(inspect(self.root, result)['usable_command_success'])
        self.plan['requirements'] = ['REQ-001']
        (self.root/'plan.json').write_text(json.dumps(self.plan, indent=2))
        self.assertEqual(inspect(self.root, result)['freshness'], 'STALE')

    def test_failure_is_current_but_not_success(self):
        result = self.run_command('raise SystemExit(5)')
        self.assertEqual(result['exit_code'], 5)
        state = inspect(self.root, result)
        self.assertEqual(state['freshness'], 'CURRENT')
        self.assertFalse(state['usable_command_success'])

    def test_timeout_and_start_failure(self):
        result = self.run_command('import time; time.sleep(60)', timeout=.1)
        self.assertEqual(result['status'], 'TIMED_OUT')
        result = execute(self.root, 'plan.json', self.root/'missing.json', ['/nonexistent/launchpad-command'])
        self.assertEqual(result['status'], 'START_FAILED')
        self.assertFalse(inspect(self.root, result)['usable_command_success'])

    def test_modification_during_run_invalidates_success(self):
        result = self.run_command("from pathlib import Path; Path('app.txt').write_text('changed')")
        self.assertEqual(result['status'], 'COMMAND_SUCCEEDED')
        self.assertFalse(result['stable_during_run'])
        self.assertFalse(inspect(self.root, result)['usable_command_success'])

    def test_deleted_file_invalidates_evidence(self):
        result = self.run_command('pass')
        (self.root/'app.txt').unlink()
        self.assertEqual(inspect(self.root, result)['freshness'], 'INVALID')

    def test_invalid_plans_do_not_execute(self):
        for change in ({'files': ['../outside']}, {'files': ['app.txt','app.txt']},
                       {'requirements': ['REQ-999']}, {'files': []}):
            with self.subTest(change=change):
                original = self.plan.copy()
                self.plan.update(change)
                self.save_plan()
                with self.assertRaises(ValueError):
                    self.run_command("raise RuntimeError('must not run')")
                self.assertFalse((self.root/'result.json').exists())
                self.plan = original

    def test_symlink_rejected(self):
        (self.root/'alias').symlink_to(self.root/'app.txt')
        self.plan['files'] = ['alias']
        self.save_plan()
        with self.assertRaises(ValueError):
            snapshot(self.root, 'plan.json')

    def test_no_overwrite_or_shell_expansion(self):
        command = [sys.executable, '-S', '-c', "import sys; assert sys.argv[1] == '$(touch injected)'", '$(touch injected)']
        result = execute(self.root, 'plan.json', self.root/'result.json', command)
        self.assertEqual(result['status'], 'COMMAND_SUCCEEDED')
        self.assertFalse((self.root/'injected').exists())
        with self.assertRaises(FileExistsError):
            self.run_command("from pathlib import Path; Path('injected').touch()")
        self.assertFalse((self.root/'injected').exists())

    def test_unittest_evidence_not_accepted(self):
        with self.assertRaises(ValueError):
            inspect(self.root, {'schema_version':1, 'status':'PASS'})
