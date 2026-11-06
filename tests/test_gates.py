"""Verification gates and reuse preparation: the sandboxed paths (lint, git, launch, tests, clone) and failure modes."""
import json
import os
import stat
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import helpers
from reqanalyzer import gates, reuse, sandbox

HAVE = bool(sandbox.bwrap_bin()) and sandbox.self_test()["ok"]


def tmp():
    return Path(tempfile.mkdtemp(prefix="gates-"))


@unittest.skipUnless(HAVE, "bubblewrap sandbox unavailable")
class SandboxedGateTests(unittest.TestCase):
    def test_run_tests_detection(self):
        w = tmp()
        self.assertEqual(gates.run_tests(w)["status"], "none")
        g, _ = gates.g_tests(w)
        self.assertEqual(g["status"], gates.FAILED)  # a build with no tests cannot pass
        (w / "tests").mkdir()
        (w / "tests" / "test_a.py").write_text("import unittest\nclass T(unittest.TestCase):\n    def test_x(self): pass\n")
        r = gates.run_tests(w)
        self.assertEqual((r["status"], r["passed"]), ("passed", 1))
        (w / "tests" / "test_b.py").write_text("import unittest\nclass U(unittest.TestCase):\n    def test_y(self): self.fail()\n")
        self.assertEqual(gates.run_tests(w)["status"], "failed")

    def test_tests_cannot_reach_network_or_home(self):
        w = tmp()
        (w / "tests").mkdir()
        (w / "tests" / "test_net.py").write_text(
            "import os, socket, unittest\nclass T(unittest.TestCase):\n"
            "    def test_offline(self):\n"
            "        with self.assertRaises(OSError):\n"
            "            socket.create_connection(('1.1.1.1', 443), timeout=2)\n"
            "        self.assertEqual(os.listdir(os.path.expanduser('~')), [])\n")
        self.assertEqual(gates.run_tests(w)["status"], "passed")

    def test_lint(self):
        w = tmp()
        self.assertEqual(gates.g_lint(w)["status"], gates.NOT_VERIFIED)
        (w / ".venv" / "bin").mkdir(parents=True)
        ruff = w / ".venv" / "bin" / "ruff"
        ruff.write_text("#!/bin/sh\necho 'x.py:1:1: F401 unused'\nexit 1\n")
        ruff.chmod(ruff.stat().st_mode | stat.S_IEXEC)
        g = gates.g_lint(w)
        self.assertEqual(g["status"], gates.FAILED)
        self.assertIn("F401", g["evidence"])
        ruff.write_text("#!/bin/sh\nexit 0\n")
        self.assertEqual(gates.g_lint(w)["status"], gates.VERIFIED)

    def test_git(self):
        w = tmp()
        self.assertEqual(gates.g_git(w, False)["status"], gates.NA)
        self.assertEqual(gates.g_git(w, True)["status"], gates.FAILED)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
        subprocess.run(["git", "init", "-q", str(w)], check=True)
        (w / "a.txt").write_text("a")
        subprocess.run(["git", "-C", str(w), "add", "."], check=True)
        subprocess.run(["git", "-C", str(w), "commit", "-qm", "x"], check=True, env=env)
        self.assertEqual(gates.g_git(w, True)["status"], gates.VERIFIED)
        (w / "b.txt").write_text("b")
        self.assertEqual(gates.g_git(w, True)["status"], gates.NOT_VERIFIED)

    def test_git_fsmonitor_hook_cannot_touch_host(self):
        """A malicious repo config (core.fsmonitor) runs only inside the sandbox, and is disabled anyway."""
        w = tmp()
        subprocess.run(["git", "init", "-q", str(w)], check=True)
        marker = tmp() / "pwned"
        subprocess.run(["git", "-C", str(w), "config", "core.fsmonitor", f"touch {marker}; false"], check=True)
        gates.g_git(w, True)
        self.assertFalse(marker.exists())

    def test_launch(self):
        w = tmp()
        web = "Web app (browser UI + local server)"
        self.assertEqual(gates.g_launch(w, 5000, "CLI tool")["status"], gates.NA)
        self.assertEqual(gates.g_launch(w, 5000, web)["status"], gates.FAILED)  # no run.sh
        (w / "run.sh").write_text("#!/bin/sh\nexec python3 -m http.server \"$1\" --bind 127.0.0.1\n")
        self.assertEqual(gates.g_launch(w, None, web)["status"], gates.NOT_VERIFIED)
        port = helpers.free_port()
        (w / "run.sh").write_text(f"#!/bin/sh\nexec python3 -m http.server {port} --bind 127.0.0.1\n")
        self.assertEqual(gates.g_launch(w, port, web)["status"], gates.VERIFIED)
        busy = __import__("socket").socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        try:
            self.assertEqual(gates.g_launch(w, busy.getsockname()[1], web)["status"], gates.NOT_VERIFIED)
        finally:
            busy.close()

    def test_launch_app_that_never_answers(self):
        w = tmp()
        (w / "run.sh").write_text("#!/bin/sh\nexit 1\n")
        old = gates.http_ok
        gates.http_ok = lambda port, deadline: old(port, 2)
        try:
            self.assertEqual(gates.g_launch(w, helpers.free_port(), "REST API service")["status"], gates.FAILED)
        finally:
            gates.http_ok = old

    def test_run_all_and_report(self):
        w = tmp()
        for f in gates.REQUIRED_DOCS + ("docs/COMPLETION_REPORT.md",):
            (w / f).parent.mkdir(parents=True, exist_ok=True)
            (w / f).write_text("x")
        (w / "tests").mkdir()
        (w / "tests" / "test_a.py").write_text("import unittest\nclass T(unittest.TestCase):\n    def test_x(self): pass\n")
        gs, t = gates.run_all(w, {"app_name": "x", "reuse": [], "git": False, "app_type": "CLI tool"}, {"mode": "new"})
        status, reasons = gates.decide(gs)
        self.assertEqual(status, "succeeded", reasons)
        md = gates.report_markdown({"id": "j1", "status": status}, gs)
        self.assertIn("| Test suite passes (re-run independently) | yes | VERIFIED |", md)


class OsvTests(unittest.TestCase):
    def serve(self, body):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}/v1/querybatch"

    def test_vulnerable_and_clean(self):
        deps = [{"ecosystem": "PyPI", "name": "flask", "version": "0.12"}, {"ecosystem": "PyPI", "name": "ok", "version": "1"}]
        old = gates.OSV_URL
        try:
            gates.OSV_URL = self.serve({"results": [{"vulns": [{"id": "GHSA-xxxx"}]}, {}]})
            g = gates.g_vulns(deps)
            self.assertEqual(g["status"], gates.FAILED)
            self.assertIn("GHSA-xxxx", g["evidence"])
            gates.OSV_URL = self.serve({"results": [{}, {}]})
            self.assertEqual(gates.g_vulns(deps)["status"], gates.VERIFIED)
            gates.OSV_URL = "file:///etc/passwd"
            self.assertEqual(gates.osv_check(deps)[0], gates.NOT_VERIFIED)
        finally:
            gates.OSV_URL = old

    def test_provenance_gate(self):
        w = tmp()
        self.assertEqual(gates.g_provenance(w, [])["status"], gates.NA)
        self.assertEqual(gates.g_provenance(w, ["x"])["status"], gates.FAILED)
        (w / "docs").mkdir()
        (w / "docs" / "REUSE_PROVENANCE.md").write_text("x")
        (w / "upstream").mkdir()
        (w / ".git").mkdir()
        self.assertEqual(gates.g_provenance(w, ["x"])["status"], gates.FAILED)  # clones would be committed
        (w / ".gitignore").write_text("upstream/\n")
        self.assertEqual(gates.g_provenance(w, ["x"])["status"], gates.VERIFIED)

    def test_dependencies_edge_cases(self):
        w = tmp()
        (w / "pyproject.toml").write_text('[project]\ndependencies = ["httpx==0.27.0", "rich"]\n')
        (w / "package-lock.json").write_text(json.dumps({"packages": {"": {}, "node_modules/a": {"version": "1.0.0"}}}))
        meta = w / ".venv" / "lib" / "python3.12" / "site-packages" / "rich-13.7.1.dist-info"
        meta.mkdir(parents=True)
        (meta / "METADATA").write_text("Metadata-Version: 2.1\nName: rich\nVersion: 13.7.1\n")
        deps = {d["name"]: d for d in gates.dependencies(w)}
        self.assertEqual(deps["rich"]["version"], "13.7.1")  # installed version wins over the unpinned declaration
        self.assertEqual(deps["a"]["ecosystem"], "npm")
        (w / "pyproject.toml").write_text("not = [valid")
        gates.dependencies(w)  # malformed manifests are tolerated, not fatal


class CloneTests(unittest.TestCase):
    """reuse.clone_repo with the sandbox call replaced: checks argv hardening and SHA reading from git's files."""

    def setUp(self):
        self.orig_run = sandbox.run
        self.addCleanup(setattr, sandbox, "run", self.orig_run)
        self.clone = helpers.reuse_real_clone

    def fake_run(self, layout):
        def run(spec, argv, timeout_s, **kw):
            self.argv, self.spec = argv, spec
            dest = Path(spec.workdir) / argv[-1]
            if layout == "fail":
                return {"code": 128, "output": "fatal: repository not found", "egress": []}
            (dest / ".git" / "refs" / "heads").mkdir(parents=True)
            sha = "a" * 40
            if layout == "loose":
                (dest / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
                (dest / ".git" / "refs" / "heads" / "main").write_text(sha + "\n")
            elif layout == "packed":
                (dest / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
                (dest / ".git" / "packed-refs").write_text(f"# pack-refs\n{sha} refs/heads/main\n")
            else:
                (dest / ".git" / "HEAD").write_text("not-a-sha\n")
            return {"code": 0, "output": "", "egress": []}
        return run

    def test_layouts(self):
        from reqanalyzer import policy
        for layout, want in (("loose", "a" * 40), ("packed", "a" * 40), ("garbage", None)):
            sandbox.run = self.fake_run(layout)
            w = tmp()
            r = self.clone(policy.parse_github_url("https://github.com/o/r/tree/dev/sub"), w / "upstream" / "o__r", w)
            self.assertEqual((r["ok"], r["sha"]), (True, want), layout)
        for flag in ("core.hooksPath=/dev/null", "protocol.file.allow=never", "--no-recurse-submodules", "--depth"):
            self.assertIn(flag, self.argv)
        self.assertEqual(self.argv[self.argv.index("--branch") + 1], "dev")
        self.assertEqual(self.spec.egress, sandbox.EGRESS_GITHUB)  # GitHub only, no credentials
        self.assertEqual(self.spec.files_ro, ())

    def test_failures_recorded(self):
        sandbox.run = self.fake_run("fail")
        old = reuse.clone_repo
        reuse.clone_repo = self.clone
        try:
            w = tmp()
            recs = reuse.prepare(w, ["GitHub · o/r · 80% · MIT · https://github.com/o/r"])
            self.assertIn("clone failed", recs[0]["decision"])

            def unavailable(*a, **k):
                raise sandbox.SandboxUnavailable("no bwrap")
            sandbox.run = unavailable
            recs = reuse.prepare(w, ["GitHub · o/r · 80% · MIT · https://github.com/o/r"])
            self.assertIn("no bwrap", recs[0]["decision"])
        finally:
            reuse.clone_repo = old


if __name__ == "__main__":
    unittest.main()
