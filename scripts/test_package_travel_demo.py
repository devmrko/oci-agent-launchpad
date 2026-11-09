import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from package_travel_demo import build, verify, FILES, BUNDLE
from spec_evidence import execute


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.base.cleanup)
        cls.source = Path(cls.base.name)
        repo = Path(__file__).resolve().parents[1]
        for name in FILES:
            target = cls.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / name, target)
        cls.evidence = execute(cls.source, Path(BUNDLE), cls.source / "evidence.json")
        if cls.evidence["status"] != "PASS":
            raise AssertionError(cls.evidence)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "source"
        shutil.copytree(self.source, self.root)
        self.output = Path(temp.name) / "demo.zip"

    def test_extract_and_run_without_original_checkout(self):
        (self.root / ".env").write_text("EXAMPLE_ONLY=true\n")
        result = build(self.root, self.evidence, self.output)
        self.assertEqual(result["status"], "PACKAGED")
        self.assertEqual(verify(self.output)["status"], "HASHES_MATCH")
        extracted = self.output.parent / "extracted"
        with zipfile.ZipFile(self.output) as archive:
            self.assertNotIn(".env", archive.namelist())
            archive.extractall(extracted)
        command = subprocess.run([sys.executable, "-S", "examples/enterprise-ai-web/cli.py", "14"], cwd=extracted,
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertEqual(json.loads(command.stdout)["amount"], 1400000)
        tests = subprocess.run([sys.executable, "-S", "-m", "unittest", "discover", "-s", "examples/enterprise-ai-web", "-p", "test_*.py"],
                               cwd=extracted, capture_output=True, text=True, timeout=60)
        self.assertEqual(tests.returncode, 0, tests.stderr)

    def test_stale_evidence_cannot_package(self):
        path = self.root / FILES[0]
        path.write_text(path.read_text()+"# changed\n")
        with self.assertRaises(ValueError):
            build(self.root, self.evidence, self.output)
        self.assertFalse(self.output.exists())

    def test_failed_or_other_evidence_rejected(self):
        for changes in ({"status": "NOT_PASSED"}, {"bundle": "other"}, {"tests_executed": False}):
            evidence = copy.deepcopy(self.evidence)
            evidence.update(changes)
            with self.assertRaises(ValueError):
                build(self.root, evidence, self.output)

    def test_existing_archive_not_overwritten(self):
        self.output.write_bytes(b"original")
        with self.assertRaises(ValueError):
            build(self.root, self.evidence, self.output)
        self.assertEqual(self.output.read_bytes(), b"original")

    def test_missing_source_rejected(self):
        (self.root / FILES[0]).unlink()
        with self.assertRaises(ValueError):
            build(self.root, self.evidence, self.output)

    def test_modified_archive_rejected(self):
        build(self.root, self.evidence, self.output)
        altered = self.output.parent / "altered.zip"
        with zipfile.ZipFile(self.output) as source, zipfile.ZipFile(altered, "w") as target:
            for name in source.namelist():
                target.writestr(name, b"changed" if name == FILES[0] else source.read(name))
        with self.assertRaises(ValueError):
            verify(altered)

    def test_external_archive_path_rejected(self):
        build(self.root, self.evidence, self.output)
        with zipfile.ZipFile(self.output, "a") as archive:
            archive.writestr("../outside.txt", "not extracted")
        with self.assertRaises(ValueError):
            verify(self.output)
