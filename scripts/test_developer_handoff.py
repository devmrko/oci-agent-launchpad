import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from developer_handoff import prepare, inspect
from spec_init import initialize


class DeveloperHandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        initialize(self.root, "spec", "비용 합산", "비용을 합산한다", ["두 정수 비용의 합계를 반환한다"])
        self.app = self.root / "cost.py"
        self.app.write_text("def total(a, b):\n    return a + b\n")
        self.test = self.root / "test_cost.py"
        self.test.write_text("import unittest\nfrom cost import total\nclass CostTests(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total(2, 3), 5)\n")
        self.manifest = self.root / "spec/traceability.json"
        data = json.loads(self.manifest.read_text())
        data["requirements"][0].update(implementation=["cost.py"], tests=[{"path": "test_cost.py", "case": "CostTests.test_total"}])
        self.manifest.write_text(json.dumps(data))
        self.output = self.root / "handoff"

    def make(self, **changes):
        values = dict(root=self.root, bundle="spec", requirements=["REQ-001"], request="음수 비용을 거부하도록 확장", acceptance=["음수 입력은 ValueError", "기존 양수 합산 유지"], output=self.output)
        values.update(changes)
        return prepare(**values)

    def test_packet_contains_context_without_copying_source_or_approving(self):
        before = self.app.read_bytes()
        baseline = self.make()
        self.assertEqual({p.name for p in self.output.iterdir()}, {"TASK.md", "baseline.json"})
        task = (self.output / "TASK.md").read_text()
        for value in ("두 정수 비용", "음수 입력", "cost.py", "CostTests.test_total"):
            self.assertIn(value, task)
        self.assertFalse(baseline["tests_executed"])
        self.assertFalse(baseline["approval_recorded"])
        self.assertEqual(self.app.read_bytes(), before)
        self.assertEqual(inspect(self.root, baseline)["status"], "UNCHANGED")

    def test_unknown_requirement_and_invalid_input_do_not_write(self):
        for changes in ({"requirements": ["REQ-999"]}, {"acceptance": []}, {"request": ""}, {"bundle": "../escape"}):
            with self.assertRaises(ValueError):
                self.make(**changes)
            self.assertFalse(self.output.exists())

    def test_existing_packet_preserved(self):
        self.make()
        original = (self.output / "baseline.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.make()
        self.assertEqual((self.output / "baseline.json").read_bytes(), original)

    def test_removed_code_requires_review(self):
        baseline = self.make()
        self.app.unlink()
        self.assertEqual(inspect(self.root, baseline)["status"], "REVIEW_REQUIRED")

    def test_external_project_change_failure_then_success_through_cli(self):
        baseline = self.make()
        self.test.write_text(self.test.read_text()+"    def test_negative(self):\n        with self.assertRaises(ValueError):\n            total(-1, 2)\n")
        data = json.loads(self.manifest.read_text())
        data["requirements"][0]["tests"].append({"path":"test_cost.py", "case":"CostTests.test_negative"})
        self.manifest.write_text(json.dumps(data))
        report = inspect(self.root, baseline)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertIn("test_cost.py", report["changed_files"])
        runner = Path(__file__).with_name("spec_evidence.py")
        def run(name):
            return subprocess.run([sys.executable, "-S", str(runner), "run", "spec", "--root", str(self.root),
                                   "--output", str(self.root / name)], capture_output=True, text=True, timeout=30)
        failed = run("failed.json")
        self.assertEqual(failed.returncode, 2, failed.stderr)
        self.assertEqual(json.loads(failed.stdout)["status"], "NOT_PASSED")
        self.app.write_text("def total(a, b):\n    if a < 0 or b < 0:\n        raise ValueError('negative')\n    return a + b\n")
        passed = run("passed.json")
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(json.loads(passed.stdout)["status"], "PASS")
        checked = subprocess.run([sys.executable, str(runner), "check", str(self.root / "passed.json"), "--root", str(self.root)], capture_output=True, text=True, timeout=10)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertTrue(json.loads(checked.stdout)["usable_pass"])
        self.assertFalse(inspect(self.root, baseline)["implementation_accepted"])
