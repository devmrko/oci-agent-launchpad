import http.client
import json
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace as Item
from server import Server, assess, estimate


class EstimateTests(unittest.TestCase):
    def test_rule_amounts(self):
        for nights in (1, 2, 10, 11, 14):
            result = estimate(nights)
            self.assertEqual(result["amount"], nights * 100000)
            self.assertFalse(result["model_used"])

    def test_invalid_nights(self):
        for value in (True, 0, 15, -1, "2", 2.5, None):
            with self.assertRaises(ValueError):
                estimate(value)


class ResultTests(unittest.TestCase):
    def result(self, output="200000\n", status="completed", answer="20만 원"):
        response = Item(status="completed", output_text=answer)
        calls = [Item(status=status, outputs=[Item(type="logs", logs=output)])]
        return assess(response, calls, 200000, True)

    def test_wrong_calculation_is_not_verified(self):
        result = self.result("300000\n")
        self.assertTrue(result["tool_verified"])
        self.assertFalse(result["calculation_verified"])
        self.assertEqual(result["verification"], "calculation_mismatch")

    def test_empty_answer_and_failed_tool_do_not_pass(self):
        self.assertEqual(self.result(answer=" ")["verification"], "incomplete_answer")
        self.assertEqual(self.result(status="failed")["verification"], "missing_tool_output")

    def test_correct_output_matches(self):
        self.assertEqual(self.result()["verification"], "calculation_verified")

    def test_plain_answer_does_not_claim_tool_verification(self):
        result = assess(Item(status="completed", output_text="20만 원"), [], 200000, False)
        self.assertEqual(result["verification"], "answer_received")
        self.assertFalse(result["calculation_verified"])


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def runner(project, region, value):
            self.calls.append(value)
            return {"answer": "200000", "completed": True}
        self.server = Server(0, "test-project", "test-region", runner)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, value, origin=None, token=None, path="/api/run"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("POST", path, json.dumps(value), {
            "Content-Type": "application/json",
            "Origin": origin or f"http://127.0.0.1:{self.server.server_port}",
            "X-Demo-Token": self.server.token if token is None else token,
        })
        response = connection.getresponse()
        status, body = response.status, response.read()
        connection.close()
        return status, body

    def test_offline_estimate_never_calls_model(self):
        self.server.offline = True
        status, body = self.post({"nights": 2}, path="/api/estimate")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["amount"], 200000)
        self.assertFalse(json.loads(body)["model_used"])
        self.assertEqual(self.server.remaining, 10)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.post({"nights": 2, "use_tool": False})[0], 409)
        self.assertEqual(self.calls, [])

    def test_extended_nights_api_and_page(self):
        for nights, amount in ((10, 1000000), (11, 1100000), (14, 1400000)):
            status, body = self.post({"nights": nights}, path="/api/estimate")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["amount"], amount)
        self.assertEqual(self.post({"nights": 15}, path="/api/estimate")[0], 400)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.server.remaining, 10)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET", "/")
        response = connection.getresponse()
        page = response.read().decode()
        connection.close()
        self.assertEqual(response.status, 200)
        import re
        options = re.findall(r'<option value="(\d+)"', page)
        self.assertEqual(options, [str(n) for n in range(1, 15)])

    def test_estimate_access_and_fields(self):
        self.assertEqual(self.post({"nights": 2}, path="/api/estimate", origin="https://example.org")[0], 403)
        self.assertEqual(self.post({"nights": 2, "rate": 1}, path="/api/estimate")[0], 400)

    def test_invalid_inputs_never_reach_oci(self):
        for nights in [True, 0, 15, "2", 2.5]:
            self.assertEqual(self.post({"nights": nights, "use_tool": False})[0], 400)
        self.assertEqual(self.calls, [])

    def test_cross_origin_and_missing_token_rejected(self):
        value = {"nights": 2, "use_tool": False}
        self.assertEqual(self.post(value, origin="https://example.org")[0], 403)
        self.assertEqual(self.post(value, token="")[0], 403)
        self.assertEqual(self.calls, [])

    def test_limit_is_enforced_before_model_call(self):
        self.server.remaining = 1
        value = {"nights": 2, "use_tool": False}
        self.assertEqual(self.post(value)[0], 200)
        self.assertEqual(self.post(value)[0], 429)
        self.assertEqual(len(self.calls), 1)

    def test_provider_error_does_not_leak_body(self):
        def failing(*args):
            raise RuntimeError("private-provider-detail")
        self.server.runner = failing
        status, body = self.post({"nights": 2, "use_tool": False})
        self.assertEqual(status, 502)
        self.assertNotIn(b"private-provider-detail", body)
        self.assertEqual(self.server.remaining, 9)


class LocalBindingTests(unittest.TestCase):
    def test_server_starts_without_name_lookup(self):
        with patch("socket.getfqdn", side_effect=AssertionError("Unexpected name lookup")) as lookup:
            with Server(0, offline=True) as server:
                self.assertEqual(server.server_address[0], "127.0.0.1")
                self.assertEqual(server.server_name, "127.0.0.1")
                self.assertGreater(server.server_port, 0)
            lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
