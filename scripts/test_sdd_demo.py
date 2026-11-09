from pathlib import Path
import tempfile
import unittest
from sdd_demo import run_demo


class WalkthroughTests(unittest.TestCase):
    def test_complete_flow_preserves_original_and_exposes_pending_review(self):
        root = Path(__file__).resolve().parents[1]
        implementation = root / "examples/enterprise-ai-web/server.py"
        original = implementation.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            result = run_demo(root, output)
            self.assertEqual(result["status"], "DEMO_PASS",
                             (output / "workspace/test-evidence.json").read_text())
            self.assertFalse(result["human_approval"])
            self.assertEqual(result["draft"]["unresolved"], 1)
            self.assertEqual(result["initial"]["review"]["requirements"][1]["status"], "DRAFT")
            self.assertEqual(result["after_interview_change"]["evidence"]["recorded_status"], "PASS")
            self.assertFalse(result["after_code_change"]["evidence"]["usable_pass"])
            self.assertEqual(implementation.read_bytes(), original)
            summary = (output / "summary.json").read_bytes()
            with self.assertRaises(FileExistsError):
                run_demo(root, output)
            self.assertEqual((output / "summary.json").read_bytes(), summary)
