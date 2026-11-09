import json
from pathlib import Path
import tempfile
import unittest
from check_spec_links import check


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "specs").mkdir()
        for name in ("spec", "design", "tasks"):
            (self.root / "specs" / f"{name}.md").write_text("## REQ-001 Example\n")
        (self.root / "app.py").write_text("pass\n")
        (self.root / "test_app.py").write_text("class TestApp:\n    def test_example(self): pass\n")
        self.data = {"requirements": [{"id": "REQ-001", "implementation": ["app.py"],
                     "tests": [{"path": "test_app.py", "case": "TestApp.test_example"}]}]}

    def run_check(self):
        (self.root / "specs/traceability.json").write_text(json.dumps(self.data))
        return check(self.root, "specs")

    def test_links_do_not_claim_test_execution(self):
        result = self.run_check()
        self.assertFalse(result["tests_executed"])
        self.assertEqual(len(result["files"]["app.py"]), 64)

    def test_unmapped_requirement_fails(self):
        (self.root / "specs/spec.md").write_text("## REQ-001 One\n## REQ-002 Two\n")
        with self.assertRaises(ValueError):
            self.run_check()

    def test_missing_test_fails(self):
        self.data["requirements"][0]["tests"][0]["case"] = "TestApp.test_missing"
        with self.assertRaises(ValueError):
            self.run_check()

    def test_external_file_fails(self):
        self.data["requirements"][0]["implementation"] = ["../outside.py"]
        with self.assertRaises(ValueError):
            self.run_check()
