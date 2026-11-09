import json
from pathlib import Path
import tempfile
import unittest

from check_spec_links import check
from spec_evidence import execute
from spec_init import initialize


class StarterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def create(self, **changes):
        values = dict(root=self.root, output="feature", title="비용 합산", purpose="사용자가 비용 합계를 확인합니다.",
                      requirements=["두 금액을 더한 값을 반환한다."])
        values.update(changes)
        return initialize(**values)

    def test_draft_has_no_review_or_test_claim(self):
        result = self.create()
        self.assertEqual(result["status"], "DRAFT")
        self.assertFalse(result["tests_executed"])
        self.assertFalse(result["review_recorded"])
        self.assertIn("두 금액을 더한 값을 반환한다.", (self.root / "feature/spec.md").read_text())
        self.assertEqual(len(list((self.root / "feature").iterdir())), 4)
        with self.assertRaisesRegex(ValueError, "Empty mapping"):
            check(self.root, "feature")

    def test_existing_bundle_preserved(self):
        self.create()
        before = {p.name: p.read_bytes() for p in (self.root / "feature").iterdir()}
        with self.assertRaises(ValueError):
            self.create(title="changed")
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / "feature").iterdir()})

    def test_invalid_inputs_create_nothing(self):
        for values in ({"requirements": []}, {"requirements": ["same", "same"]},
                       {"requirements": ["line\n## REQ-002"]}, {"title": ""}, {"purpose": "\t"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.create(**values)
            self.assertFalse((self.root / "feature").exists())

    def test_external_paths_rejected(self):
        for output in ("../escape", str(self.root / "absolute")):
            with self.assertRaises(ValueError):
                self.create(output=output)
        (self.root / "link").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.create(output="link/escape")

    def test_multiple_requirements_keep_stable_order(self):
        self.create(requirements=["first", "second"])
        data = json.loads((self.root / "feature/traceability.json").read_text())
        self.assertEqual([r["id"] for r in data["requirements"]], ["REQ-001", "REQ-002"])

    def test_real_mapping_connects_to_existing_evidence_runner(self):
        self.create()
        (self.root / "cost.py").write_text("def total(a, b):\n    return a + b\n")
        (self.root / "test_cost.py").write_text(
            "import unittest\nfrom cost import total\nclass CostTests(unittest.TestCase):\n"
            "    def test_total(self):\n        self.assertEqual(total(100, 200), 300)\n")
        path = self.root / "feature/traceability.json"
        data = json.loads(path.read_text())
        data["requirements"][0].update(implementation=["cost.py"], tests=[{"path": "test_cost.py", "case": "CostTests.test_total"}])
        path.write_text(json.dumps(data))
        self.assertEqual(check(self.root, "feature")["status"], "links_valid")
        result = execute(self.root, Path("feature"), self.root / "evidence.json")
        self.assertEqual(result["status"], "PASS")

    def test_dangling_output_symlink_is_not_followed(self):
        (self.root / "feature").symlink_to(self.root / "missing", target_is_directory=True)
        with self.assertRaises(ValueError):
            self.create()
        self.assertFalse((self.root / "missing").exists())

    def test_delivery_is_optional_and_does_not_add_requirements(self):
        self.create()
        self.assertNotIn("제공 형태 메모", (self.root / "feature/spec.md").read_text())

    def test_freeform_delivery_notes_preserve_requirements_and_tasks(self):
        self.create(delivery=["API와 웹 화면을 함께 제공", "야간 파일 처리 배치도 검토"])
        spec = (self.root / "feature/spec.md").read_text()
        self.assertIn("API와 웹 화면을 함께 제공", spec)
        self.assertIn("야간 파일 처리 배치도 검토", spec)
        data = json.loads((self.root / "feature/traceability.json").read_text())
        self.assertEqual(len(data["requirements"]), 1)
        self.assertNotIn("야간 파일", (self.root / "feature/tasks.md").read_text())
        self.create(output="plain")
        for name in ("design.md", "tasks.md", "traceability.json"):
            self.assertEqual((self.root / "plain" / name).read_bytes(), (self.root / "feature" / name).read_bytes())

    def test_invalid_delivery_is_rejected_before_writing(self):
        for value in ([""], ["line\n## REQ-999"], "api", ["api"] * 101):
            with self.assertRaises(ValueError):
                self.create(delivery=value)
            self.assertFalse((self.root / "feature").exists())
