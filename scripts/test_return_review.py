import json
from pathlib import Path
import unittest

import test_developer_handoff as fixtures
from developer_handoff import report
from spec_evidence import execute


class ReturnReviewTests(unittest.TestCase):
    setUp = fixtures.DeveloperHandoffTests.setUp
    make = fixtures.DeveloperHandoffTests.make

    def evidence(self, name="evidence.json"):
        return execute(self.root, Path("spec"), self.root / name)

    def review(self, baseline, evidence):
        return report(self.root, baseline, evidence, self.root / "review")

    def test_current_pass_keeps_acceptance_pending(self):
        result = self.review(self.make(), self.evidence())
        self.assertEqual(result["status"], "TESTS_CURRENT_REVIEW_PENDING")
        self.assertTrue(all(item["status"] == "HUMAN_REVIEW_PENDING" for item in result["acceptance"]))
        self.assertFalse(result["approval_recorded"])
        self.assertFalse(result["implementation_accepted"])
        self.assertFalse(result["tests_executed"])
        self.assertIn("- [ ] 음수 입력", (self.root / "review/REVIEW.md").read_text())

    def test_missing_evidence_needs_checks(self):
        result = self.review(self.make(), None)
        self.assertEqual(result["status"], "CHECKS_REQUIRED")
        self.assertIn("test_evidence_missing", result["reasons"])

    def test_code_change_stales_passing_evidence(self):
        baseline, evidence = self.make(), self.evidence()
        self.app.write_text(self.app.read_text()+"# changed\n")
        result = self.review(baseline, evidence)
        self.assertEqual(result["evidence"]["freshness"], "STALE")
        self.assertEqual(result["status"], "CHECKS_REQUIRED")
        self.assertIn("cost.py", result["changes"]["changed_files"])

    def test_failed_test_is_not_current_pass(self):
        baseline = self.make()
        self.app.write_text("def total(a, b):\n    return 0\n")
        result = self.review(baseline, self.evidence())
        self.assertEqual(result["status"], "CHECKS_REQUIRED")
        self.assertEqual(result["evidence"]["recorded_status"], "NOT_PASSED")

    def test_other_bundle_rejected_without_output(self):
        baseline, evidence = self.make(), self.evidence()
        evidence["bundle"] = "other"
        with self.assertRaises(ValueError):
            self.review(baseline, evidence)
        self.assertFalse((self.root / "review").exists())

    def test_replaced_test_is_highlighted_even_when_passed(self):
        baseline = self.make()
        self.test.write_text(self.test.read_text().replace("test_total", "test_replacement"))
        data = json.loads(self.manifest.read_text())
        data["requirements"][0]["tests"][0]["case"] = "CostTests.test_replacement"
        self.manifest.write_text(json.dumps(data))
        result = self.review(baseline, self.evidence())
        self.assertTrue(result["evidence"]["usable_pass"])
        self.assertEqual(result["status"], "CHECKS_REQUIRED")
        self.assertEqual(result["removed_tests"][0]["case"], "CostTests.test_total")

    def test_missing_selected_requirement_needs_checks(self):
        baseline = self.make()
        spec = self.root / "spec/spec.md"
        spec.write_text(spec.read_text().replace("REQ-001", "REQ-002"))
        data = json.loads(self.manifest.read_text())
        data["requirements"][0]["id"] = "REQ-002"
        self.manifest.write_text(json.dumps(data))
        result = self.review(baseline, self.evidence())
        self.assertEqual(result["missing_requirements"], ["REQ-001"])
        self.assertEqual(result["status"], "CHECKS_REQUIRED")

    def test_existing_review_not_overwritten(self):
        baseline, evidence = self.make(), self.evidence()
        self.review(baseline, evidence)
        original = (self.root / "review/review.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.review(baseline, evidence)
        self.assertEqual((self.root / "review/review.json").read_bytes(), original)
