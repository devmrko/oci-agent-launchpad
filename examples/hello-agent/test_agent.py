import json
import unittest
from datetime import datetime
from agent import execute, run, demo_decision, validate


class HelloTests(unittest.TestCase):
    def test_demo_clock_pipeline(self):
        result = run("서울은 지금 몇 시인가요?", demo_decision, "demo")
        self.assertFalse(result["model_used"])
        self.assertEqual(result["decision"]["tool"], "get_time")
        stamp = datetime.fromisoformat(result["tool_result"]["time"])
        self.assertEqual(stamp.utcoffset().total_seconds(), 9 * 3600)
        self.assertIn(result["tool_result"]["time"], result["answer"])

    def test_unknown_tools_and_arguments_rejected(self):
        for decision in [
            {"tool": "shell", "arguments": {"command": "echo unsafe"}},
            {"tool": "get_time", "arguments": {"city": "Paris"}},
            {"tool": "get_time", "arguments": {"city": []}},
            {"tool": "greet", "arguments": {"code": "anything"}},
            {"tool": "greet", "arguments": {}, "override": True},
        ]:
            with self.subTest(decision=decision), self.assertRaises(ValueError):
                execute(decision)

    def test_invalid_model_output_does_not_execute(self):
        with self.assertRaises(ValueError):
            run("서울 시간", lambda _: "not json", "oci")

    def test_unsupported(self):
        result = run("계좌 이체해줘", demo_decision, "demo")
        self.assertEqual(result["decision"]["tool"], "unsupported")

    def test_greeting(self):
        self.assertIn("안녕하세요", run("안녕하세요", demo_decision, "demo")["answer"])

    def test_input_bounds(self):
        for message in ["", " " * 3, "x" * 1001]:
            with self.assertRaises(ValueError):
                run(message, demo_decision, "demo")


if __name__ == "__main__":
    unittest.main()
