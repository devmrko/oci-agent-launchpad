import json
import os
from pathlib import Path
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adapters.codex_exec import main


class CodexAdapterTests(unittest.TestCase):
    def test_zero_exit_requires_fresh_nonempty_response(self):
        for response in (None, "", "   ", "Implemented the requested change"):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                task = Path(directory) / "TASK.md"
                task.write_text("Synthetic task")
                prior = Path.cwd()
                try:
                    os.chdir(directory)
                    def run(*args, **kwargs):
                        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
                        if response is not None:
                            Path("CODEX_RESULT.md").write_text(response)
                        return SimpleNamespace(returncode=0)
                    with patch("sys.argv", ["adapter", str(task)]), patch("shutil.which", return_value="/tool/codex"), patch("subprocess.run", side_effect=run):
                        self.assertEqual(main(), 0 if response and response.strip() else 3)
                    result = json.loads(Path("ADAPTER_RESULT.json").read_text())
                    self.assertEqual(result["status"], "RESPONSE_RECEIVED" if response and response.strip() else "EMPTY_RESPONSE")
                    self.assertFalse(result["implementation_accepted"])
                finally:
                    os.chdir(prior)

    def test_previous_response_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            prior = Path.cwd()
            try:
                os.chdir(directory)
                Path("TASK.md").write_text("Synthetic task")
                Path("CODEX_RESULT.md").write_text("Old success")
                with patch("sys.argv", ["adapter", "TASK.md"]), patch("shutil.which", return_value="/tool/codex"), patch("subprocess.run") as invoke, patch("sys.stderr"):
                    with self.assertRaises(SystemExit):
                        main()
                    invoke.assert_not_called()
            finally:
                os.chdir(prior)

    def test_command_preserves_sandbox_and_records_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "TASK.md"
            task.write_text("Synthetic task")
            prior = Path.cwd()
            try:
                os.chdir(directory)
                with patch("sys.argv", ["adapter", str(task)]), patch("shutil.which", return_value="/tool/codex"), patch("subprocess.run", return_value=SimpleNamespace(returncode=7)) as invoke:
                    self.assertEqual(main(), 7)
                command = invoke.call_args.args[0]
                self.assertEqual(command[:4], ["/tool/codex", "exec", "--sandbox", "workspace-write"])
                self.assertIn("--ephemeral", command)
                self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
                self.assertIn(str(task), command[-1])
                result = json.loads(Path("ADAPTER_RESULT.json").read_text())
                self.assertEqual(result["exit_code"], 7)
                self.assertFalse(result["implementation_accepted"])
            finally:
                os.chdir(prior)

    def test_missing_tool_does_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "TASK.md"
            task.write_text("Synthetic task")
            with patch("sys.argv", ["adapter", str(task)]), patch("shutil.which", return_value=None), patch("subprocess.run") as invoke, patch("sys.stderr"):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                invoke.assert_not_called()
