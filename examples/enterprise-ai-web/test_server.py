import http.client
import json
import threading
import unittest
from server import Server, validate


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

    def post(self, value, origin=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("POST", "/api/run", json.dumps(value), {
            "Content-Type": "application/json",
            "Origin": origin or f"http://127.0.0.1:{self.server.server_port}",
            "X-Demo-Token": self.server.token if token is None else token,
        })
        response = connection.getresponse()
        status, body = response.status, response.read()
        connection.close()
        return status, body

    def test_invalid_inputs_never_reach_oci(self):
        for nights in [True, 0, 11, "2", 2.5]:
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


if __name__ == "__main__":
    unittest.main()
