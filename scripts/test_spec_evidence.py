import json
from pathlib import Path
import tempfile
import unittest
from spec_evidence import execute, inspect


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "specs").mkdir()
        for name in ("spec", "design", "tasks"):
            (self.root / "specs" / f"{name}.md").write_text("## REQ-001 Example\n")
        (self.root / "app.py").write_text("pass\n")
        (self.root / "specs/traceability.json").write_text(json.dumps({"requirements": [
            {"id": "REQ-001", "implementation": ["app.py"], "tests": [
                {"path": "test_app.py", "case": "TestApp.test_example"}]}]}))
        self.output = self.root / "evidence.json"

    def run_case(self, body="pass", decorator="", timeout=5):
        (self.root / "test_app.py").write_text(
            f"import unittest\nclass TestApp(unittest.TestCase):\n    {decorator}\n    def test_example(self):\n        {body}\n")
        return execute(self.root, Path("specs"), self.output, timeout)

    def test_pass_and_freshness(self):
        result = self.run_case()
        self.assertEqual(result["requirements"], {"REQ-001": "PASS"})
        self.assertTrue(inspect(self.root, result)["usable_pass"])
        (self.root / "app.py").write_text("changed = True\n")
        report = inspect(self.root, result)
        self.assertEqual(report["freshness"], "STALE")
        self.assertFalse(report["usable_pass"])

    def test_failed_test_stays_failed_when_current(self):
        result = self.run_case("self.fail('sensitive message')")
        self.assertEqual(result["status"], "NOT_PASSED")
        self.assertFalse(inspect(self.root, result)["usable_pass"])
        self.assertNotIn("sensitive message", self.output.read_text())

    def test_skip_is_not_pass(self):
        self.assertEqual(self.run_case(decorator="@unittest.skip('reason')")["status"], "NOT_PASSED")

    def test_expected_failure_is_not_pass(self):
        self.assertEqual(self.run_case("self.fail()", "@unittest.expectedFailure")["status"], "NOT_PASSED")

    def test_timeout_is_not_pass(self):
        result = self.run_case("import time; time.sleep(2)", timeout=0.1)
        self.assertEqual(result["tests"][0]["status"], "TIMEOUT")
        self.assertEqual(result["status"], "NOT_PASSED")

    def test_change_during_execution_invalidates(self):
        result = self.run_case("from pathlib import Path; Path('app.py').write_text('changed')")
        self.assertEqual(result["status"], "INVALIDATED")
        self.assertFalse(inspect(self.root, result)["usable_pass"])

    def test_existing_output_is_not_overwritten(self):
        self.output.write_text("original")
        with self.assertRaises(ValueError):
            self.run_case("self.fail()")
        self.assertEqual(self.output.read_text(), "original")

    def test_runtime_error_is_not_pass(self):
        result = self.run_case("raise RuntimeError('private')")
        self.assertEqual(result["status"], "NOT_PASSED")
        self.assertEqual(result["tests"][0]["counts"]["errors"], 1)

    def test_missing_file_invalidates_evidence(self):
        result = self.run_case()
        (self.root / "app.py").unlink()
        self.assertEqual(inspect(self.root, result)["freshness"], "INVALID")

    def test_invalid_timeout_rejected(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.run_case(timeout=timeout)
