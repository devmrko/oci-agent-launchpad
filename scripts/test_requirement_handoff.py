import copy
import json
from pathlib import Path
import tempfile
import unittest
from requirement_handoff import draft, review, status, snapshot


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.bundle = self.root / "bundle"
        self.data = json.loads((Path(__file__).resolve().parents[1] / "specs/interview-handoff/interview.example.json").read_text())
        self.save()

    def save(self):
        self.source.write_text(json.dumps(self.data))

    def test_drafts_and_deferred_are_separate(self):
        result = draft(self.source, self.bundle)
        self.assertEqual(result, {"status": "DRAFT", "requirements": 2, "unresolved": 1})
        report = status(self.bundle)
        self.assertEqual(report["scope"], "captured_snapshot_only")
        self.assertTrue(all(r["status"] == "DRAFT" for r in report["requirements"]))

    def test_review_and_requirement_change(self):
        draft(self.source, self.bundle)
        review(self.bundle, "REQ-001", "synthetic-reviewer")
        self.assertEqual(status(self.bundle)["requirements"][0]["status"], "REVIEW_RECORDED")
        path = self.bundle / "requirements.json"
        data = json.loads(path.read_text())
        data["requirements"][0]["text"] = "Changed requirement"
        path.write_text(json.dumps(data))
        self.assertEqual(status(self.bundle)["requirements"][0]["status"], "REVIEW_REQUIRED")
        self.assertEqual(len(list((self.bundle / "reviews").glob("*.json"))), 1)

    def test_source_correction_requires_review(self):
        draft(self.source, self.bundle)
        review(self.bundle, "REQ-001", "synthetic-reviewer")
        self.data["revision"] = 2
        corrected = copy.deepcopy(self.data["answers"][0])
        corrected.update(id="a-4", supersedes="a-1", text="숙박 상한을 14박으로 변경")
        self.data["answers"].append(corrected)
        self.save()
        report = status(self.bundle, self.source)
        self.assertTrue(report["source_changed"])
        self.assertEqual(report["requirements"][0]["status"], "REVIEW_REQUIRED")

    def test_other_project_rejected(self):
        draft(self.source, self.bundle)
        self.data["id"] = "another-project"
        self.save()
        with self.assertRaises(ValueError):
            status(self.bundle, self.source)

    def test_duplicate_and_branch_rejected(self):
        self.data["answers"].append(copy.deepcopy(self.data["answers"][0]))
        with self.assertRaises(ValueError):
            snapshot(self.data)
        self.data["answers"][-1]["id"] = "a-4"
        with self.assertRaises(ValueError):
            snapshot(self.data)

    def test_output_is_never_overwritten(self):
        draft(self.source, self.bundle)
        original = (self.bundle / "requirements.json").read_bytes()
        with self.assertRaises(FileExistsError):
            draft(self.source, self.bundle)
        self.assertEqual((self.bundle / "requirements.json").read_bytes(), original)

    def test_forged_evidence_rejected(self):
        draft(self.source, self.bundle)
        path = self.bundle / "requirements.json"
        data = json.loads(path.read_text())
        data["requirements"][0]["answer_ids"] = ["other-answer"]
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            review(self.bundle, "REQ-001", "synthetic-reviewer")
