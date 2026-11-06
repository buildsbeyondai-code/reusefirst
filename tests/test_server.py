"""HTTP API tests against a real server instance on an ephemeral port."""
import http.client
import io
import json
import threading
import time
import unittest
from contextlib import redirect_stdout

import helpers
from reqanalyzer import cli, server


class ServerTests(unittest.TestCase):
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

    def req(self, method, path, body=None, headers=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json", "X-ReqAn-Token": server.SESSION_TOKEN} | (headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def test_index_and_assets(self):
        for path, ctype in (("/", "text/html"), ("/app.js", "text/javascript"), ("/app.css", "text/css"),
                            ("/theme.js", "text/javascript")):
            st, h, b = self.req("GET", path)
            self.assertEqual(st, 200)
            self.assertTrue(h["Content-Type"].startswith(ctype))
            self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertIn(b"Reuse-First Builder", self.req("GET", "/")[2])

    def test_health(self):
        st, _, b = self.req("GET", "/api/health")
        d = json.loads(b)
        self.assertEqual((st, d["ok"], d["catalog_size"]), (200, True, 4))
        # status strip fields (UEUIS §8.11): real capability checks, never guesses
        self.assertTrue(d["claude_cli"] and d["standard_found"] and d["ui_standard_found"])
        self.assertIs(d["github_authenticated"], False)  # tests never read a real token
        self.assertIs(d["build_running"], False)

    def test_analyze(self):
        st, _, b = self.req("POST", "/api/analyze", {"requirement": "Stripe invoicing with PDF invoices", "top": 3})
        d = json.loads(b)
        self.assertEqual(st, 200)
        self.assertEqual(d["github"][0]["name"], "acme/stripe-invoices")
        self.assertLessEqual(len(d["claude_plugins"]), 3)

    def test_analysis_history_saved_with_timestamp(self):
        before = time.time()
        st, _, b = self.req("POST", "/api/analyze", {"requirement": "History check: Stripe invoicing",
                                                      "keywords": ["pdf"], "github": False})
        self.assertEqual(st, 200)
        saved = json.loads(b)["saved"]
        self.assertGreaterEqual(saved["created_at"], before - 1)
        self.assertRegex(saved["id"], r"^\d{8}T\d{9}Z-[0-9a-f]{6}$")
        st, _, b = self.req("GET", "/api/analyses")
        listed = json.loads(b)["analyses"]
        self.assertEqual(st, 200)
        self.assertEqual(listed[0]["id"], saved["id"])  # newest first
        self.assertEqual(listed[0]["requirement"], "History check: Stripe invoicing")
        st, _, b = self.req("GET", f"/api/analyses/{saved['id']}")
        rec = json.loads(b)
        self.assertEqual((st, rec["keywords"], rec["github"]), (200, ["pdf"], False))
        self.assertEqual(rec["result"]["requirement"], "History check: Stripe invoicing")
        self.assertNotIn("saved", rec["result"])
        # delete needs the session token
        self.assertEqual(self.req("POST", f"/api/analyses/{saved['id']}/delete", {}, headers={"X-ReqAn-Token": "wrong"})[0], 403)
        tok = {"X-ReqAn-Token": server.SESSION_TOKEN}
        self.assertEqual(self.req("POST", f"/api/analyses/{saved['id']}/delete", {}, headers=tok)[0], 200)
        self.assertEqual(self.req("GET", f"/api/analyses/{saved['id']}")[0], 404)
        self.assertEqual(self.req("POST", f"/api/analyses/{saved['id']}/delete", {}, headers=tok)[0], 404)

    def test_analysis_history_rejects_bad_ids(self):
        for bad in ("..%2Fx", "abc", "20261105T000000000Z-zzzzzz"):
            self.assertEqual(self.req("GET", f"/api/analyses/{bad}")[0], 404)

    def test_history_keeps_newest(self):
        import tempfile
        from pathlib import Path

        from reqanalyzer import history
        h = history.History(Path(tempfile.mkdtemp()))
        old = history.MAX_KEEP
        history.MAX_KEEP = 3
        try:
            ids = []
            for i in range(5):
                ids.append(h.save({"requirement": f"r{i}"})["id"])
                time.sleep(0.002)
        finally:
            history.MAX_KEEP = old
        self.assertEqual(len(list(h.dir.glob("*.json"))), 3)
        self.assertEqual([x["id"] for x in h.list()], ids[:-4:-1])  # the 3 newest kept, newest first

    def test_reload(self):
        st, _, b = self.req("POST", "/api/reload", {})
        self.assertEqual((st, json.loads(b)["catalog_size"]), (200, 4))

    def test_rejects_foreign_host(self):  # DNS-rebinding protection
        self.assertEqual(self.req("GET", "/", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/analyze", {"requirement": "x"}, headers={"Host": "evil.example:5057"})[0], 403)

    def test_rejects_form_posts(self):  # cross-site form CSRF protection
        st = self.req("POST", "/api/analyze", raw=b"requirement=x",
                      headers={"Content-Type": "application/x-www-form-urlencoded"})[0]
        self.assertEqual(st, 415)

    def test_bad_requests(self):
        self.assertEqual(self.req("POST", "/api/analyze", raw=b"{bad")[0], 400)
        self.assertEqual(self.req("POST", "/api/analyze", raw=b"[1]")[0], 400)
        self.assertEqual(self.req("POST", "/api/analyze", {"requirement": ""})[0], 400)
        self.assertEqual(self.req("POST", "/api/analyze", {"requirement": "x", "top": "abc"})[0], 400)
        self.assertEqual(self.req("POST", "/api/analyze", raw=b"x" * (server.MAX_BODY + 1))[0], 413)
        self.assertEqual(self.req("GET", "/nope")[0], 404)
        self.assertEqual(self.req("GET", "/../server.py")[0], 404)
        self.assertEqual(self.req("POST", "/api/other", {})[0], 404)

    def test_port_in_use_exits_76(self):
        self.assertEqual(server.main(["--port", str(self.port)]), 76)


class CliTests(unittest.TestCase):
    def setUp(self):
        helpers.use_fixture_catalog()

    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(list(args))
        return code, buf.getvalue()

    def test_json_and_markdown(self):
        code, out = self.run_cli("--no-github", "Stripe invoicing with PDF invoices")
        self.assertEqual((code, json.loads(out)["claude_plugins"][0]["name"]), (0, "invoice-maker"))
        code, out = self.run_cli("--no-github", "--markdown", "-k", "billing", "Stripe invoicing")
        self.assertIn("| invoice-maker", out)
        self.assertIn("**Verdict:**", out)

    def test_markdown_handles_no_results(self):
        code, out = self.run_cli("--no-github", "--markdown", "zzzqqq")
        self.assertIn("none found", out)

    def test_empty_requirement_exit_2(self):
        import sys
        sys.stdin = io.StringIO("")
        self.assertEqual(self.run_cli("--no-github", "")[0], 2)


if __name__ == "__main__":
    unittest.main()
