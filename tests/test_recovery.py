"""Crash recovery, fallbacks and failure paths: swap journal recovery, two-step swap, storage cap, launch errors,
sandbox degradation, and the server entry point."""
import io
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import helpers
from reqanalyzer import builder, gates, sandbox, server
from test_builder import answers, wait
from test_enhance import enhance_answers, make_app


def tmp():
    return Path(tempfile.mkdtemp(prefix="recov-"))


class SwapRecoveryTests(unittest.TestCase):
    def mgr_with(self, job):
        state = tmp()
        (state / "builds" / job["id"]).mkdir(parents=True)
        (state / "builds" / job["id"] / "job.json").write_text(json.dumps(job))
        return builder.BuildManager(state)

    def job(self, target, staging, prev, state, ino):
        return {"id": "j-swap", "app_name": "x", "mode": "enhance", "output_dir": str(target), "status": "verifying",
                "created_at": time.time(), "started_at": time.time(), "finished_at": None, "events": [],
                "transitions": [], "swap": {"state": state, "target": str(target), "staging": str(staging),
                                            "previous": str(prev), "staging_ino": ino, "carry": ["data"]}}

    def test_exchange_completed_then_crash_finishes_carry_over(self):
        root = tmp()
        target, staging, prev = root / "app", root / "stg", root / "prev"
        target.mkdir()
        (target / "new.py").write_text("new")
        prev.mkdir()
        (prev / "data").mkdir()
        (prev / "data" / "db").write_text("user")
        m = self.mgr_with(self.job(target, staging, prev, "exchanging", target.stat().st_ino))
        j = m.get("j-swap")
        self.assertTrue(j["applied"])
        self.assertEqual((target / "data" / "db").read_text(), "user")
        self.assertEqual(j["status"], "interrupted")

    def test_exchange_never_happened(self):
        root = tmp()
        target, staging = root / "app", root / "stg"
        target.mkdir()
        staging.mkdir()
        m = self.mgr_with(self.job(target, staging, root / "prev", "exchanging", staging.stat().st_ino))
        self.assertFalse(m.get("j-swap")["applied"])

    def test_two_step_crash_between_renames(self):
        root = tmp()
        target, staging, prev = root / "app", root / "stg", root / "prev"
        staging.mkdir()
        prev.mkdir()
        ino = staging.stat().st_ino
        m = self.mgr_with(self.job(target, staging, prev, "two-step", ino))
        self.assertTrue(m.get("j-swap")["applied"])
        self.assertTrue(target.is_dir())

    def test_two_step_crash_with_staging_lost_restores_previous(self):
        root = tmp()
        target, staging, prev = root / "app", root / "stg", root / "prev"
        prev.mkdir()
        (prev / "orig.py").write_text("orig")
        m = self.mgr_with(self.job(target, staging, prev, "two-step", 0))
        self.assertFalse(m.get("j-swap")["applied"])
        self.assertEqual((target / "orig.py").read_text(), "orig")  # the user's app is back


class FallbackTests(unittest.TestCase):
    def setUp(self):
        os.environ["FAKE_CLAUDE_MODE"] = "ok"
        self.mgr = builder.BuildManager(helpers.TMP / f"state-{self._testMethodName}")

    def test_two_step_swap_when_renameat2_unavailable(self):
        app = make_app("two-step-app")
        old = builder.exchange

        def unsupported(a, b):
            raise OSError(38, "Function not implemented")
        builder.exchange = unsupported
        try:
            j = wait(self.mgr, self.mgr.start("x", enhance_answers(app), {})["id"])
        finally:
            builder.exchange = old
        self.assertEqual(j["status"], "succeeded", j.get("reasons"))
        self.assertTrue((app / "app.py").exists())
        self.assertEqual((app / "data" / "jobs.sqlite3").read_text(), "user data")

    def test_storage_cap_stops_build(self):
        os.environ["FAKE_CLAUDE_MODE"] = "slow"
        old = (builder.MAX_PROJECT_BYTES, builder.SIZE_CHECK_S, builder.MINUTE_S)
        builder.MAX_PROJECT_BYTES, builder.SIZE_CHECK_S, builder.MINUTE_S = 10, 0.1, 2.0
        try:
            j = wait(self.mgr, self.mgr.start("r", answers("bigproj", reuse=[]))["id"], timeout=60)
        finally:
            builder.MAX_PROJECT_BYTES, builder.SIZE_CHECK_S, builder.MINUTE_S = old
            os.environ["FAKE_CLAUDE_MODE"] = "ok"
        self.assertEqual(j["status"], "failed")
        self.assertIn("grew beyond", j["error"])

    def test_sandbox_start_failure_is_reported(self):
        old = builder.sandbox.Run

        def boom(*a, **k):
            raise sandbox.SandboxUnavailable("bwrap vanished")
        builder.sandbox.Run = boom
        try:
            j = wait(self.mgr, self.mgr.start("r", answers("nosbx-run", reuse=[]))["id"])
        finally:
            builder.sandbox.Run = old
        self.assertEqual(j["status"], "failed")
        self.assertIn("bwrap vanished", j["error"])

    def test_launch_error_paths(self):
        j = wait(self.mgr, self.mgr.start("r", answers("launch-err", reuse=[], port=helpers.free_port()))["id"])
        self.assertEqual(j["status"], "succeeded", j.get("reasons"))
        job = self.mgr.jobs[j["id"]]
        busy = socket.socket()
        busy.bind(("127.0.0.1", job["port"]))
        busy.listen(1)
        try:
            with self.assertRaisesRegex(builder.BuildError, "already in use"):
                self.mgr.launch(j["id"])
        finally:
            busy.close()
        old_http = gates.http_ok
        gates.http_ok = lambda port, deadline: (False, "no answer")
        try:
            with self.assertRaisesRegex(builder.BuildError, "did not answer"):
                self.mgr.launch(j["id"])
        finally:
            gates.http_ok = old_http
        port = job.pop("port")
        with self.assertRaisesRegex(builder.BuildError, "no port"):
            self.mgr.launch(j["id"])
        job["port"] = port
        (Path(job["output_dir"]) / "run.sh").unlink()
        with self.assertRaisesRegex(builder.BuildError, "no run.sh"):
            self.mgr.launch(j["id"])

    def test_helpers(self):
        d = tmp()
        (d / "a").write_bytes(b"x" * 100)
        (d / "b").write_bytes(b"x" * 100)
        self.assertGreater(builder.dir_bytes(d, 50), 50)
        self.assertEqual(builder.dir_bytes(d, 10_000), 200)
        self.assertIsNone(builder.proc_start(10 ** 9))
        self.assertFalse(builder.BuildManager._kill_orphan({"pid": 10 ** 9, "proc_start": "1"}))
        a, b = tmp(), tmp()
        (a / "x").write_text("a")
        builder.exchange(a, b)
        self.assertTrue((b / "x").exists())
        with self.assertRaises(OSError):
            builder.exchange(tmp() / "missing", b)


class SandboxDegradationTests(unittest.TestCase):
    def test_no_scope_means_rlimit_only(self):
        old = sandbox._scope_ok
        os.environ["REQAN_NO_SCOPE"] = "1"
        sandbox._scope_ok = None
        try:
            self.assertFalse(sandbox.scope_available())
            self.assertEqual(sandbox.resource_prefix(sandbox.Spec(workdir=tmp())), [])
        finally:
            del os.environ["REQAN_NO_SCOPE"]
            sandbox._scope_ok = old

    def test_self_test_reports_broken_bwrap(self):
        old, old_st = os.environ.get("REQAN_BWRAP"), sandbox._self_test
        os.environ["REQAN_BWRAP"] = "/bin/false"
        try:
            st = sandbox.self_test(force=True)
            self.assertFalse(st["ok"])
            self.assertIn("did not start", st["error"])
        finally:
            if old is None:
                os.environ.pop("REQAN_BWRAP", None)
            else:
                os.environ["REQAN_BWRAP"] = old
            sandbox._self_test = old_st

    def test_toolchain_override(self):
        os.environ["REQAN_SANDBOX_TOOLCHAIN"] = f"{tmp()}:/nonexistent"
        try:
            self.assertEqual(len(sandbox.toolchain_paths()), 1)
        finally:
            del os.environ["REQAN_SANDBOX_TOOLCHAIN"]


class ServerMainTests(unittest.TestCase):
    def test_port_in_use_exits_76(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        try:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(server.main(["--port", str(s.getsockname()[1])]), 76)
        finally:
            s.close()

    def test_non_linux_refused(self):
        old = server.sys.platform
        server.sys.platform = "win32"
        try:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(server.main(["--port", "1"]), 78)
        finally:
            server.sys.platform = old

    def test_hook_refuses_old_python_quietly(self):
        hook = helpers.ROOT / "plugins" / "req-analyzer" / "hooks" / "ensure_server.py"
        r = subprocess.run(["python3", "-c", f"import sys; sys.version_info=(3,10,0); sys.argv=['x']; exec(open({str(hook)!r}).read())"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertIn("needs Linux or WSL2 with Python 3.11+", r.stderr)


if __name__ == "__main__":
    unittest.main()
