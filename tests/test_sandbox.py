"""Harmless adversarial tests of the execution sandbox (audit A1, A2). Needs bubblewrap; skipped when absent."""
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import helpers  # noqa: F401  (environment)
from reqanalyzer import sandbox

HAVE = bool(sandbox.bwrap_bin()) and sandbox.self_test()["ok"]
PY = os.path.realpath(__import__("sys").executable)


def run(code, **spec):
    w = Path(tempfile.mkdtemp(prefix="sbx-test-"))
    r = sandbox.run(sandbox.Spec(workdir=w, **spec), [PY, "-I", "-c", code], timeout_s=60)
    return r, w


@unittest.skipUnless(HAVE, "bubblewrap sandbox unavailable")
class IsolationTests(unittest.TestCase):
    def test_self_test_all_checks(self):
        st = sandbox.self_test(force=True)
        self.assertTrue(st["ok"], st)
        for k in ("secrets_hidden", "home_empty", "host_state_hidden", "host_loopback_blocked", "direct_egress_blocked",
                  "proxy_denies_unlisted", "env_clean", "docker_socket_absent", "no_capabilities", "pid_namespace"):
            self.assertTrue(st["checks"][k], k)

    def test_cannot_write_outside_project(self):
        outside = Path(tempfile.mkdtemp(prefix="sbx-outside-"))
        r, w = run(f"open({str(outside / 'pwned')!r}, 'w').write('x')")
        self.assertNotEqual(r["code"], 0)
        self.assertFalse((outside / "pwned").exists())

    def test_credential_and_home_read_attempts(self):
        r, _ = run("import os,glob; print(sorted(glob.glob(os.path.expanduser('~/*')) + glob.glob(os.path.expanduser('~/.*'))))")
        self.assertEqual(r["output"].strip(), "[]")

    def test_env_is_cleared(self):
        os.environ["REQAN_SECRET_PROBE"] = "s3cret"
        try:
            r, _ = run("import os; print('REQAN_SECRET_PROBE' in os.environ)")
        finally:
            del os.environ["REQAN_SECRET_PROBE"]
        self.assertEqual(r["output"].strip(), "False")

    def test_host_localhost_service_unreachable(self):
        ls = socket.socket()
        ls.bind(("127.0.0.1", 0))
        ls.listen(1)
        try:
            r, _ = run(f"import socket; s=socket.socket(); s.settimeout(2); print(s.connect_ex(('127.0.0.1', {ls.getsockname()[1]})))")
        finally:
            ls.close()
        self.assertNotEqual(r["output"].strip(), "0")

    def test_egress_allowlist(self):
        """A local HTTPS-less target stands in for an allowed host: CONNECT is allowed only for listed names."""
        ls = socket.socket()
        ls.bind(("127.0.0.1", 0))
        ls.listen(5)
        port = ls.getsockname()[1]

        def echo():
            c, _ = ls.accept()
            c.sendall(b"hello-from-allowed")
            c.close()
        threading.Thread(target=echo, daemon=True).start()
        old = sandbox._host_allowed
        try:
            code = ("import socket\n"
                    "def via(host, port):\n"
                    "    s = socket.create_connection(('127.0.0.1', 3128), timeout=5)\n"
                    "    s.sendall(f'CONNECT {host}:{port} HTTP/1.1\\r\\n\\r\\n'.encode())\n"
                    "    return s.recv(200)\n"
                    "print(via('evil.example', 443)[:12])\n"
                    "print(via('localhost', 443)[:12])\n")
            r, _ = run(code, egress=frozenset({"localhost"}))
        finally:
            ls.close()
            sandbox._host_allowed = old
        lines = r["output"].splitlines()
        self.assertIn("403", lines[0])  # not in the allowlist
        self.assertIn("403", lines[1])  # allowlisted name but non-public address: refused (no host loopback via proxy)
        self.assertTrue(any(not e["allowed"] for e in r["egress"]))

    def test_proxy_refuses_plain_http_and_other_ports(self):
        code = ("import socket\n"
                "s = socket.create_connection(('127.0.0.1', 3128), timeout=5)\n"
                "s.sendall(b'GET http://example.com/ HTTP/1.1\\r\\n\\r\\n'); print(s.recv(40))\n"
                "s = socket.create_connection(('127.0.0.1', 3128), timeout=5)\n"
                "s.sendall(b'CONNECT example.com:22 HTTP/1.1\\r\\n\\r\\n'); print(s.recv(40))\n")
        r, _ = run(code, egress=frozenset({"example.com"}))
        self.assertEqual(r["output"].count("403"), 2, r["output"])

    def test_timeout_kills_process_tree(self):
        w = Path(tempfile.mkdtemp(prefix="sbx-test-"))
        code = "import subprocess,time; subprocess.Popen(['sleep','301']); time.sleep(300)"
        r = sandbox.run(sandbox.Spec(workdir=w), [PY, "-I", "-c", code], timeout_s=2)
        self.assertTrue(r["timed_out"])
        time.sleep(0.5)
        out = os.popen("pgrep -f '^sleep 301$' || true").read().strip()
        self.assertEqual(out, "")  # no orphan

    def test_launch_forwarding_and_isolation(self):
        w = Path(tempfile.mkdtemp(prefix="sbx-app-"))
        (w / "index.html").write_text("ok")
        port = helpers.free_port()
        r = sandbox.Run(sandbox.Spec(workdir=w, inbound_port=port), [PY, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                        stdout=open(os.devnull, "w"), stderr=open(os.devnull, "w"))
        try:
            from reqanalyzer import gates
            ok, why = gates.http_ok(port, 15)
            self.assertTrue(ok, why)
        finally:
            r.close()
        ok, _ = __import__("reqanalyzer.gates", fromlist=["x"]).http_ok(port, 1)
        self.assertFalse(ok)  # stopped


class FailClosedTests(unittest.TestCase):
    def test_missing_bwrap_blocks(self):
        old_env, old = os.environ.get("REQAN_BWRAP"), sandbox._self_test
        os.environ["REQAN_BWRAP"] = ""
        sandbox._self_test = None
        orig = sandbox.bwrap_bin
        sandbox.bwrap_bin = lambda: None
        try:
            st = sandbox.self_test(force=True)
            self.assertFalse(st["ok"])
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.require()
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.Run(sandbox.Spec(workdir=Path(tempfile.mkdtemp())), ["true"])
        finally:
            sandbox.bwrap_bin = orig
            sandbox._self_test = old
            if old_env is None:
                os.environ.pop("REQAN_BWRAP", None)
            else:
                os.environ["REQAN_BWRAP"] = old_env

    def test_bwrap_args_shape(self):
        w = Path(tempfile.mkdtemp())
        a = sandbox.bwrap_args(sandbox.Spec(workdir=w), Path("/tmp/s"))
        for flag in ("--unshare-all", "--die-with-parent", "--new-session", "--clearenv"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--cap-drop") + 1], "ALL")
        self.assertNotIn("--share-net", a)
        binds = [a[i + 1] for i, x in enumerate(a) if x == "--bind"]
        self.assertEqual(binds, [str(w.resolve()), "/tmp/s"])  # only the project (and the socket dir) are writable
        self.assertNotIn(str(Path.home()), [a[i + 1] for i, x in enumerate(a) if x in ("--bind", "--ro-bind")])


if __name__ == "__main__":
    unittest.main()
