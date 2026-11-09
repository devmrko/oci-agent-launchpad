import json
from pathlib import Path
import subprocess
import sys
import unittest
from allowance import estimate


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, "-S", str(Path(__file__).with_name("cli.py")), *args],
                              capture_output=True, text=True, timeout=5)

    def test_json_matches_shared_rule(self):
        for nights in (1, 2, 10, 11, 14):
            with self.subTest(nights=nights):
                result = self.invoke(str(nights))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(json.loads(result.stdout), estimate(nights))

    def test_invalid_input_has_no_success_output(self):
        for args in (("0",), ("15",), ("-1",), ("2.5",), ("true",), ("abc",), (), ("2", "3")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)
