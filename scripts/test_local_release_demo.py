from pathlib import Path
import tempfile
import unittest

from local_release_demo import demo, active_smoke, calculation_ok, runtime_matches


class LocalReleaseTests(unittest.TestCase):
    def test_real_package_execution_fault_and_rollback(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'release'
            result = demo(root, output)
            self.assertEqual(result['status'], 'LOCAL_RELEASE_PASS')
            self.assertTrue(result['source_unchanged'])
            self.assertEqual(result['new_acceptance_before_implementation'], 'NOT_PASSED')
            self.assertEqual(result['active_release'], 'a')
            self.assertFalse(runtime_matches(output/'runtime-b'))
            self.assertTrue(runtime_matches(output/'runtime-a'))
            self.assertTrue(calculation_ok(active_smoke(output)))
            self.assertNotEqual(result['releases']['a']['archive_sha256'], result['releases']['b']['archive_sha256'])
            self.assertFalse(result['deployment_performed'])
            original = (output/'summary.json').read_bytes()
            with self.assertRaises(FileExistsError):
                demo(root, output)
            self.assertEqual((output/'summary.json').read_bytes(), original)

    def test_success_exit_with_wrong_result_is_not_healthy(self):
        for result in ({'exit_code':0,'stdout':'not JSON'},
                       {'exit_code':0,'stdout':'{"amount":1,"model_used":false}'},
                       {'exit_code':0,'stdout':'{"amount":200000,"model_used":true}'}):
            self.assertFalse(calculation_ok(result))
