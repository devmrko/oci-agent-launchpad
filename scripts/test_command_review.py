import json
import sys
import unittest

import test_developer_handoff as fixtures
from developer_handoff import report
from command_evidence import execute
from spec_evidence import execute as run_tests


class CommandReviewTests(unittest.TestCase):
    setUp = fixtures.DeveloperHandoffTests.setUp
    make = fixtures.DeveloperHandoffTests.make

    def evidence(self, code='pass', files=None):
        self.baseline = self.make()
        plan = {'schema_version': 1, 'spec': 'spec/spec.md', 'requirements':['REQ-001'],
                'files': files or list(self.baseline['files'])}
        (self.root/'plan.json').write_text(json.dumps(plan))
        return execute(self.root, 'plan.json', self.root/'command.json', [sys.executable, '-S', '-c', code])

    def review(self, command, tests=None):
        return report(self.root, self.baseline, tests, self.root/'review', [command])

    def test_current_command_is_distinct_from_test_pass(self):
        result = self.review(self.evidence())
        self.assertEqual(result['status'], 'COMMANDS_CURRENT_REVIEW_PENDING')
        self.assertFalse(result['requirements_verified'])
        self.assertFalse(result['approval_recorded'])
        self.assertEqual(result['acceptance'][0]['status'], 'HUMAN_REVIEW_PENDING')
        text = (self.root/'review/REVIEW.md').read_text()
        self.assertIn('COMMAND_SUCCEEDED', text)
        self.assertIn('명령 성공은 요구별 테스트 통과 판정이 아닙니다', text)

    def test_failed_command_blocks_even_when_unittest_passes(self):
        command = self.evidence('raise SystemExit(3)')
        tests = run_tests(self.root, 'spec', self.root/'tests.json')
        result = self.review(command, tests)
        self.assertEqual(result['status'], 'CHECKS_REQUIRED')
        self.assertIn('command_evidence_not_current_success', result['reasons'])

    def test_stale_command_blocks(self):
        command = self.evidence()
        self.app.write_text(self.app.read_text()+'\n# changed\n')
        result = self.review(command)
        self.assertEqual(result['status'], 'CHECKS_REQUIRED')
        self.assertEqual(result['command_evidence'][0]['freshness'], 'STALE')

    def test_missing_file_coverage_blocks(self):
        result = self.review(self.evidence(files=['cost.py']))
        self.assertIn('command_file_coverage_incomplete', result['reasons'])
        self.assertEqual(result['status'], 'CHECKS_REQUIRED')

    def test_other_spec_rejected(self):
        command = self.evidence()
        (self.root/'other.md').write_text('## REQ-001 Other\n')
        plan = json.loads((self.root/'plan.json').read_text())
        plan['spec'] = 'other.md'
        (self.root/'plan.json').write_text(json.dumps(plan))
        with self.assertRaises(ValueError):
            self.review(command)
        self.assertFalse((self.root/'review').exists())

    def test_both_valid_keeps_existing_test_status(self):
        command = self.evidence()
        tests = run_tests(self.root, 'spec', self.root/'tests.json')
        result = self.review(command, tests)
        self.assertEqual(result['status'], 'TESTS_CURRENT_REVIEW_PENDING')
        self.assertTrue(result['command_evidence'][0]['usable_command_success'])
