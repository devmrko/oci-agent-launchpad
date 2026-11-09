import json
from pathlib import Path
import tempfile
import unittest
from requirement_handoff import draft, review, write_new
from spec_impact import bind, inspect


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        example = Path(__file__).resolve().parents[1] / "specs/interview-handoff/interview.example.json"
        self.source = self.root / "latest.json"
        self.source.write_text(example.read_text())
        draft(self.source, self.root / "handoff")
        review(self.root / "handoff", "REQ-001", "synthetic-reviewer")
        target = self.root / "target"
        target.mkdir()
        (target / "spec.md").write_text("## REQ-101 Calculate\nLimit 10 nights.\n## REQ-102 Other\nShared file.\n")
        for name in ("design.md", "tasks.md"):
            (target / name).write_text("Synthetic test document\n")
        (self.root / "app.py").write_text("RATE = 100000\n")
        (self.root / "test_app.py").write_text("class TestApp:\n    def test_amount(self): pass\n")
        manifest = {"requirements": [{"id": rid, "implementation": ["app.py"],
                     "tests": [{"path": "test_app.py", "case": "TestApp.test_amount"}]}
                     for rid in ("REQ-101", "REQ-102")]}
        (target / "traceability.json").write_text(json.dumps(manifest))
        self.baseline = self.make_binding()

    def make_binding(self, source_id="REQ-001", target="target"):
        return bind(self.root, "handoff", source_id, target, "REQ-101", self.source, "synthetic mapping")

    def report(self):
        return inspect(self.root, self.baseline, self.source)

    def test_unchanged_is_not_test_pass(self):
        result = self.report()
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertFalse(result["tests_executed"])
        self.assertEqual(result["tests_to_review"], [])

    def test_unreviewed_source_rejected(self):
        with self.assertRaises(ValueError):
            self.make_binding("REQ-002")

    def test_implementation_change_includes_shared_requirements(self):
        (self.root / "app.py").write_text("RATE = 200000\n")
        result = self.report()
        self.assertEqual(result["changed_files"], ["app.py"])
        self.assertEqual(result["potentially_affected_requirements"], ["REQ-101", "REQ-102"])
        self.assertEqual(result["tests_to_review"][0]["case"], "TestApp.test_amount")

    def test_deleted_implementation_is_not_unchanged(self):
        (self.root / "app.py").unlink()
        result = self.report()
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("app.py", result["changed_files"])

    def test_deleted_test_is_reported(self):
        (self.root / "test_app.py").write_text("class TestApp: pass\n")
        self.assertIn("target_links_invalid", self.report()["reasons"])

    def test_target_requirement_change(self):
        path = self.root / "target/spec.md"
        path.write_text(path.read_text().replace("10 nights", "14 nights"))
        self.assertIn("target_requirement_changed", self.report()["reasons"])

    def test_source_requirement_change(self):
        path = self.root / "handoff/requirements.json"
        data = json.loads(path.read_text())
        data["requirements"][0]["text"] = "Changed source requirement"
        path.write_text(json.dumps(data))
        self.assertIn("source_requirement_changed", self.report()["reasons"])

    def test_latest_source_correction(self):
        data = json.loads(self.source.read_text())
        data["revision"] += 1
        self.source.write_text(json.dumps(data))
        self.assertIn("source_review_not_current", self.report()["reasons"])

    def test_other_project_rejected(self):
        data = json.loads(self.source.read_text())
        data["id"] = "other"
        self.source.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.report()

    def test_external_target_rejected(self):
        with self.assertRaises(ValueError):
            self.make_binding(target="../outside")

    def test_mapping_change_requires_review(self):
        path = self.root / "target/traceability.json"
        data = json.loads(path.read_text())
        (self.root / "extra.py").write_text("pass\n")
        data["requirements"][0]["implementation"].append("extra.py")
        path.write_text(json.dumps(data))
        self.assertIn("target_mapping_changed", self.report()["reasons"])

    def test_existing_baseline_preserved(self):
        path = self.root / "baseline.json"
        write_new(path, self.baseline)
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            write_new(path, {"replacement": True})
        self.assertEqual(path.read_bytes(), original)
