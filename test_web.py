"""Offline tests for the local server's request checks (python -m unittest)."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

import web


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)   # any free port
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers.setdefault("Host", f"127.0.0.1:{self.port}")
        conn.request(method, path, body, {k.replace("_", "-"): v for k, v in headers.items()})
        response = conn.getresponse()
        response.data = response.read()
        conn.close()
        return response

    def restore(self, body=b'{"sheet": "1q26QtprurV563_8qTLt2yhBLBNVBv2MP8zzUk6cYmd0"}', **headers):
        headers.setdefault("Content_Type", "application/json")
        return self.call("POST", "/api/restore", body, **headers)

    def test_page_sends_security_headers(self):
        response = self.call("GET", "/")
        self.assertEqual(response.status, 200)
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
        self.assertNotIn("'unsafe-inline'", response.getheader("Content-Security-Policy").split("script-src")[1].split(";")[0])
        self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
        self.assertNotIn(b"<script>", response.data)   # all script lives in app.js, which the CSP allows

    def test_serves_only_listed_files(self):
        self.assertEqual(self.call("GET", "/app.js").status, 200)
        self.assertEqual(self.call("GET", "/icon-32.png").status, 200)
        self.assertEqual(self.call("GET", "/hero.mp4").getheader("Content-Type"), "video/mp4")
        for path in ("/web.py", "/../web.py", "/vercel.json", "/%2e%2e/cellulo.py"):
            self.assertEqual(self.call("GET", path).status, 404, path)

    def test_refuses_foreign_host(self):
        # DNS rebinding: a hostile name pointed at 127.0.0.1
        self.assertEqual(self.call("GET", "/", Host=f"evil.example:{self.port}").status, 403)
        self.assertEqual(self.restore(Host="evil.example").status, 403)

    def test_refuses_foreign_origin(self):
        self.assertEqual(self.restore(Origin="https://evil.example").status, 403)
        self.assertEqual(self.restore(Origin=f"http://localhost:{self.port}").status, 403)   # Host says 127.0.0.1

    def test_refuses_bad_lengths_and_bodies(self):
        self.assertEqual(self.restore(b"x" * 5000).status, 413)
        self.assertEqual(self.restore(b"{}", Content_Length="-1").status, 413)
        self.assertEqual(self.restore(b"not json").status, 422)
        self.assertEqual(self.restore(b'{"sheet": "https://example.com/file.pdf"}').status, 422)

    def test_restore_returns_octet_stream_with_details(self):
        meta = {"filename": "../a b.svg", "mime_type": "image/svg+xml", "byte_size": 3, "chunk_count": " 1\n", "sha256": "ab"}
        with mock.patch.object(web, "get_service"), mock.patch.object(web, "download", return_value=(meta, b"abc")):
            response = self.restore(Origin=f"http://127.0.0.1:{self.port}")
        self.assertEqual(response.status, 200, response.data)
        self.assertEqual(response.data, b"abc")
        self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
        self.assertEqual(response.getheader("X-Cellulo-Name"), "a%20b.svg")
        self.assertEqual(response.getheader("X-Cellulo-Mime"), "image/svg%2Bxml")
        self.assertEqual(response.getheader("X-Cellulo-Chunks"), "1")


if __name__ == "__main__":
    unittest.main()
