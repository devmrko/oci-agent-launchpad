import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_developer_handoff as fixtures
from developer_runner import run
from spec_evidence import execute
from developer_handoff import report


class RunnerTests(unittest.TestCase):
    setUp = fixtures.DeveloperHandoffTests.setUp
    make = fixtures.DeveloperHandoffTests.make

    def invoke(self, code, timeout=10):
        return run(self.root, self.output, self.root / "execution", [sys.executable, "-S", "-c", code], timeout)

    def test_tool_receives_task_and_returns_testable_change(self):
        self.test.write_text(self.test.read_text()+"    def test_negative(self):\n        with self.assertRaises(ValueError):\n            total(-1, 2)\n")
        mapping = json.loads(self.manifest.read_text())
        mapping["requirements"][0]["tests"].append({"path": "test_cost.py", "case": "CostTests.test_negative"})
        self.manifest.write_text(json.dumps(mapping))
        failed = execute(self.root, Path("spec"), self.root / "before-evidence.json")
        self.assertEqual(failed["status"], "NOT_PASSED")
        baseline = self.make()
        original = self.app.read_bytes()
        adapter = self.root / "adapter.py"
        adapter.write_text("import sys\nfrom pathlib import Path\nassert '음수' in Path(sys.argv[1]).read_text()\np=Path('cost.py')\np.write_text('def total(a, b):\\n    if a < 0 or b < 0:\\n        raise ValueError(\\\"negative\\\")\\n    return a + b\\n')\n")
        result = run(self.root, self.output, self.root / "execution", [sys.executable, "-S", str(adapter), "{task}"])
        self.assertEqual(result["status"], "COMMAND_SUCCEEDED")
        self.assertEqual(result["changed_files"][0]["path"], "cost.py")
        self.assertEqual(self.app.read_bytes(), original)
        self.assertIn("raise ValueError", (self.root / "execution/changes.diff").read_text())
        workspace = self.root / "execution/workspace"
        evidence = execute(workspace, Path("spec"), self.root / "evidence.json")
        self.assertEqual(evidence["status"], "PASS")
        self.assertFalse(report(workspace, baseline, evidence, self.root / "review")["implementation_accepted"])
        self.assertEqual(json.loads((self.root / "execution/status.json").read_text())["status"], "COMMAND_SUCCEEDED")

    def test_failed_command_not_success(self):
        self.make()
        result = self.invoke("raise SystemExit(7)")
        self.assertEqual(result["status"], "COMMAND_FAILED")
        self.assertEqual(result["exit_code"], 7)

    def test_timeout(self):
        self.make()
        result = self.invoke("import time; time.sleep(5)", timeout=0.1)
        self.assertEqual(result["status"], "TIMED_OUT")
        self.assertFalse(result["tests_executed"])

    def test_start_failure_recorded(self):
        self.make()
        result = run(self.root, self.output, self.root / "execution", [str(self.root / "missing-command")])
        self.assertEqual(result["status"], "START_FAILED")

    def test_stale_handoff_never_executes(self):
        self.make()
        self.app.write_text("changed")
        with self.assertRaises(ValueError):
            self.invoke("raise AssertionError('must not run')")
        self.assertFalse((self.root / "execution").exists())

    def test_existing_output_not_overwritten(self):
        self.make()
        (self.root / "execution").mkdir()
        with self.assertRaises(ValueError):
            self.invoke("raise AssertionError('must not run')")

    def test_output_symlink_not_followed(self):
        self.make()
        result = self.invoke("from pathlib import Path; Path('outside').symlink_to('/etc/passwd')")
        self.assertEqual(result["collection"], "COLLECTION_FAILED")
        self.assertFalse(result["implementation_accepted"])

    def test_cli_options_and_literal_arguments(self):
        self.make()
        script = Path(__file__).with_name("developer_runner.py")
        result = subprocess.run([sys.executable, str(script), str(self.output), "--root", str(self.root),
            "--output", str(self.root / "execution"), "--", sys.executable, "-c",
            "import sys; from pathlib import Path; Path('received.txt').write_text(sys.argv[1])", "$(not-a-shell)"],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "execution/workspace/received.txt").read_text(), "$(not-a-shell)")
