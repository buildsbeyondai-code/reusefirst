"""Security regression tests for the local HTTP API (audit findings A3-A5, A21)."""
import http.client
import json
import socket
import stat
import threading
import time
import unittest

import helpers
from reqanalyzer import server


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.use_fixture_catalog()
        cls.gh = helpers.FakeGitHub("ok")
        helpers.use_github(cls.gh)
        cls.srv = server.make_server(0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.gh.close()

    def req(self, method, path, body=None, headers=None, token=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json"} | ({"X-ReqAn-Token": server.SESSION_TOKEN} if token else {}) | (headers or {})
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        out = (r.status, r.read())
        c.close()
        return out

    def raw(self, data: bytes, wait=3.0) -> bytes:
        s = socket.create_connection(("127.0.0.1", self.port))
        s.settimeout(wait)
        s.sendall(data)
        try:
            return s.recv(200)
        except socket.timeout:
            return b"TIMEOUT"
        finally:
            s.close()


class AuthTests(Base):
    def test_sensitive_reads_need_token(self):  # regression A3
        for path in ("/api/builds", "/api/analyses", "/api/apps", "/api/builds/x", "/api/analyses/x",
                     "/api/diagnostics", "/api/outcomes"):
            with self.subTest(path=path):
                self.assertEqual(self.req("GET", path, token=False)[0], 403)
        for path in ("/api/analyze", "/api/inputs", "/api/reload", "/api/build", "/api/builds/x/launch", "/api/builds/x/stop"):
            with self.subTest(path=path):
                self.assertEqual(self.req("POST", path, {"requirement": "x"}, token=False)[0], 403)

    def test_wrong_token_rejected(self):
        self.assertEqual(self.req("GET", "/api/builds", headers={"X-ReqAn-Token": "x" * 32})[0], 403)

    def test_public_health_is_minimal(self):
        st, b = self.req("GET", "/api/health", token=False)
        d = json.loads(b)
        self.assertEqual(st, 200)
        self.assertIsInstance(d["catalog_errors"], int)  # no paths
        self.assertIn("sandbox_ok", d)

    def test_session_only_same_origin(self):
        self.assertEqual(self.req("GET", "/api/session", token=False, headers={"Sec-Fetch-Site": "same-origin"})[0], 200)
        self.assertEqual(self.req("GET", "/api/session", token=False, headers={"Sec-Fetch-Site": "same-site"})[0], 403)
        self.assertEqual(self.req("GET", "/api/session", token=False, headers={"Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_strict_mode_disables_session(self):
        server.STRICT_TOKEN = True
        try:
            self.assertEqual(self.req("GET", "/api/session", token=False)[0], 403)
        finally:
            server.STRICT_TOKEN = False

    def test_cross_origin_rejected(self):  # regression A5
        for h in ({"Origin": "https://evil.example"}, {"Origin": f"http://127.0.0.1:{self.port + 1}"},
                  {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(h=h):
                self.assertEqual(self.req("POST", "/api/analyze", {"requirement": "invoice"}, headers=h)[0], 403)
        ok = self.req("POST", "/api/analyze", {"requirement": "invoice"}, headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(ok[0], 200)

    def test_token_file_is_private(self):
        f = server.write_token_file()
        self.assertEqual(f.read_text(), server.SESSION_TOKEN)
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)

    def test_diagnostics_redacts(self):
        st, b = self.req("GET", "/api/diagnostics")
        self.assertEqual(st, 200)
        self.assertNotIn(server.SESSION_TOKEN, b.decode())
        self.assertIn("sandbox", json.loads(b))


class HttpParsingTests(Base):
    def test_negative_content_length_answers_immediately(self):  # regression A4
        t = time.time()
        out = self.raw(b"POST /api/analyze HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
                       b"X-ReqAn-Token: " + server.SESSION_TOKEN.encode() + b"\r\nContent-Length: -1\r\n\r\n{}")
        self.assertTrue(out.startswith(b"HTTP/1.0 400") or out.startswith(b"HTTP/1.1 400"), out)
        self.assertLess(time.time() - t, 2)

    def test_missing_length_and_chunked_rejected(self):
        tok = b"X-ReqAn-Token: " + server.SESSION_TOKEN.encode() + b"\r\n"
        out = self.raw(b"POST /api/analyze HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n" + tok + b"\r\n")
        self.assertIn(b" 411", out)
        out = self.raw(b"POST /api/analyze HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n" + tok +
                       b"Transfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n")
        self.assertIn(b" 400", out)

    def test_oversized_body(self):
        st, _ = self.req("POST", "/api/analyze", {"requirement": "x" * (server.MAX_BODY + 10)})
        self.assertEqual(st, 413)

    def test_stalled_client_is_dropped(self):
        old = server.Handler.timeout
        server.Handler.timeout = 1
        try:
            out = self.raw(b"POST /api/analyze HTTP/1.1\r\nHost: 127.0.0.1\r\n", wait=4)
            self.assertNotEqual(out, b"TIMEOUT")  # the server closed the connection (b"") instead of waiting forever
        finally:
            server.Handler.timeout = old

    def test_bad_values(self):
        for body in ({"requirement": "x", "top": True}, {"requirement": "x", "top": "5"}, {"requirement": 5},
                     {"requirement": "x", "keywords": "nope"}):
            with self.subTest(body=body):
                self.assertEqual(self.req("POST", "/api/analyze", body)[0], 400)
        self.assertEqual(self.req("GET", "/api/builds/..%2F..%2Fetc")[0], 404)
        self.assertEqual(self.req("GET", "/api/builds/x?since=-5")[0], 404)

    def test_concurrency_cap(self):
        old = server._inflight
        server._inflight = threading.BoundedSemaphore(1)
        server._inflight.acquire()
        try:
            self.assertEqual(self.req("GET", "/api/health", token=False)[0], 503)
        finally:
            server._inflight = old

    def test_error_responses_do_not_leak(self):
        st, b = self.req("GET", "/api/nope")
        self.assertEqual(st, 404)
        self.assertNotIn(b"Traceback", b)


if __name__ == "__main__":
    unittest.main()
