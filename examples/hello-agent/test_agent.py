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

    def test_supported_city_list_in_demo(self):
        for message in ("지원 도시", "도시 목록", "어떤 도시를 지원하나요?"):
            result = run(message, demo_decision, "demo")
            self.assertFalse(result["model_used"])
            self.assertEqual(result["decision"], {"tool": "list_cities", "arguments": {}})
            self.assertEqual(result["tool_result"]["cities"], [
                {"city": "서울", "timezone": "Asia/Seoul"},
                {"city": "도쿄", "timezone": "Asia/Tokyo"},
                {"city": "런던", "timezone": "Europe/London"},
            ])
            for city in ("서울", "도쿄", "런던"):
                self.assertIn(city, result["answer"])

    def test_city_list_rejects_extra_arguments(self):
        for arguments in ({"city": "서울"}, {"command": "anything"}, []):
            with self.assertRaises(ValueError):
                execute({"tool": "list_cities", "arguments": arguments})

    def test_english_city_list_in_demo(self):
        for message in (
            "list cities", "LIST CITIES", "LiSt CiTiEs", "  list cities  ",
            "supported cities", "SUPPORTED CITIES", "  Supported Cities  ",
            "\tSupported Cities\n", "\t지원 도시\n", "  도시 목록  ",
            "  어떤 도시를 지원하나요?  ",
        ):
            with self.subTest(message=message):
                result = run(message, demo_decision, "demo")
                self.assertFalse(result["model_used"])
                self.assertEqual(result["decision"], {"tool": "list_cities", "arguments": {}})
                self.assertEqual(result["tool_result"]["cities"], [
                    {"city": "서울", "timezone": "Asia/Seoul"},
                    {"city": "도쿄", "timezone": "Asia/Tokyo"},
                    {"city": "런던", "timezone": "Europe/London"},
                ])
                self.assertEqual(result["answer"], result["tool_result"]["message"])
                for item in result["tool_result"]["cities"]:
                    self.assertIn(item["city"], result["answer"])
                    self.assertIn(item["timezone"], result["answer"])

    def test_city_list_requires_exact_match(self):
        for message in (
            "list cities now", "  LIST CITIES NOW  ", "please list cities",
            "supported cities now", "unsupported cities", "list cities!",
            "list  cities", "supported\tcities", "run arbitrary command",
        ):
            with self.subTest(message=message):
                result = run(message, demo_decision, "demo")
                self.assertFalse(result["model_used"])
                self.assertEqual(result["decision"], {"tool": "unsupported", "arguments": {}})

    def test_input_bounds(self):
        for message in ["", " " * 3, "x" * 1001]:
            with self.assertRaises(ValueError):
                run(message, demo_decision, "demo")


if __name__ == "__main__":
    unittest.main()
