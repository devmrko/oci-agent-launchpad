"""Bridge existing fixture-free tests and exercise the real local HTTP handler."""
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import HTTPServer

from app import Handler
import test_app


class ContractTests(unittest.TestCase):
    def test_existing_service(self):
        test_app.test_service()

    def test_existing_health(self):
        test_app.test_health()

    def request(self, path):
        class LocalServer(HTTPServer):
            # Avoid hostname lookup; tests bind only to loopback.
            def server_bind(self):
                from socketserver import TCPServer
                TCPServer.server_bind(self)
                self.server_name, self.server_port = self.server_address
        server = LocalServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            connection.request('GET', path)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

    def test_root(self):
        status, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertEqual(body['status'], 'ok')
