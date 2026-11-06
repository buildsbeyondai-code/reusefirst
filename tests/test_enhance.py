"""Build tab "Enhance an existing app": listing apps, inputs, validation, backup, prompt and the build run."""
import http.client
import json
import os
import shutil
import tarfile
import threading
import unittest
from pathlib import Path

import helpers
from reqanalyzer import builder, server
from test_builder import answers, wait

APPS = Path(os.environ["REQAN_APPS_DIR"])


def make_app(name="job-finder"):
    d = APPS / name
    shutil.rmtree(d, ignore_errors=True)
    (d / "docs").mkdir(parents=True)
    (d / "data").mkdir()
    (d / ".venv" / "bin").mkdir(parents=True)
    (d / "CLAUDE.md").write_text("# CLAUDE.md\n- Job finder; tests: tools/coverage.sh\n")
    (d / "README.md").write_text("# Resume-Matched Job Finder\nFinds jobs.\n")
    (d / "BUILD_SPEC.md").write_text("ORIGINAL SPEC\n")
    (d / "data" / "jobs.sqlite3").write_text("user data")
    (d / ".env").write_text("ADZUNA_APP_KEY=secret-value-123\n")
    (d / ".venv" / "bin" / "python").symlink_to("/usr/bin/python3")
    (d / "tests").mkdir()
    (d / "tests" / "test_existing.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                                                 "    def test_ok(self):\n        self.assertTrue(True)\n")
    return d


def enhance_answers(d, **over):
    a = answers("unused", build_mode=builder.ENHANCE, output_dir=str(d), app_name=d.name, git=False)
    a.pop("port")
    a.update(over)
    return a


class EnhanceTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        (APPS / "not-an-app").mkdir(parents=True, exist_ok=True)
        (APPS / ".hidden").mkdir(parents=True, exist_ok=True)
        (APPS / ".hidden" / "README.md").write_text("x")
        self.mgr = builder.BuildManager(helpers.TMP / f"state-{self._testMethodName}")
        Path(os.environ["FAKE_CLAUDE_ARGV"]).unlink(missing_ok=True)

    def test_existing_apps_and_target_check(self):
        apps = builder.existing_apps()
        self.assertIn({"name": "job-finder", "path": str(self.app.resolve())}, apps)
        self.assertNotIn("not-an-app", [a["name"] for a in apps])
        self.assertNotIn(".hidden", [a["name"] for a in apps])
        self.assertEqual(builder.enhance_target(str(self.app)), self.app.resolve())
        for bad in (str(APPS / "not-an-app"), str(helpers.TMP), "/etc", ""):
            with self.assertRaises(builder.BuildError):
                builder.enhance_target(bad)

    def test_missing_apps_dir(self):
        old = builder.APPS_DIR
        builder.APPS_DIR = helpers.TMP / "no-such-dir"
        try:
            self.assertEqual(builder.existing_apps(), [])
        finally:
            builder.APPS_DIR = old

    def test_inputs_for_enhancement(self):
        r = builder.required_inputs("Auto apply with Naukri and LinkedIn fallback", None, str(self.app))
        by = {f["id"]: f for f in r["fields"]}
        self.assertEqual(r["mode"], "enhance")
        self.assertEqual(r["fields"][0]["id"], "build_mode")
        self.assertEqual((by["output_dir"]["default"], by["app_name"]["default"]), (str(self.app.resolve()), "job-finder"))
        self.assertNotIn("port", by)
        self.assertFalse(by["git"]["default"])
        prompt = json.loads(Path(os.environ["FAKE_CLAUDE_ARGV"]).read_text().splitlines()[-1])["argv"][1]
        self.assertIn("ENHANCEMENT of an existing app", prompt)
        self.assertIn("Job finder; tests: tools/coverage.sh", prompt)  # the app's own CLAUDE.md is context
        self.assertIn("# Resume-Matched Job Finder", prompt)
        self.assertEqual(builder.required_inputs("New invoicing app")["mode"], "new")
        with self.assertRaises(builder.BuildError):
            builder.required_inputs("x", None, "/etc")

    def test_validation(self):
        a = builder.validate_spec("req", enhance_answers(self.app))
        self.assertEqual(a["output_dir"], str(self.app.resolve()))  # non-empty folder accepted when enhancing
        with self.assertRaisesRegex(builder.BuildError, "build mode"):
            builder.validate_spec("req", enhance_answers(self.app, build_mode="Replace everything"))
        with self.assertRaisesRegex(builder.BuildError, "not an existing app"):
            builder.validate_spec("req", enhance_answers(APPS / "not-an-app"))
        with self.assertRaisesRegex(builder.BuildError, "not empty"):  # a new build still refuses existing apps
            builder.validate_spec("req", answers("x", output_dir=str(self.app)))

    def test_enhance_build(self):
        job = self.mgr.start("Auto apply via Naukri/LinkedIn when no company site", enhance_answers(self.app),
                             {"must_have": "MUST-have features"})
        j = wait(self.mgr, job["id"])
        self.assertEqual((j["status"], j["mode"]), ("succeeded", "enhance"), j.get("reasons"))
        self.assertTrue(j["applied"])
        self.assertEqual(j["baseline_tests"]["status"], "passed")
        self.assertEqual({g["id"]: g for g in j["gates"]}["regression"]["status"], "VERIFIED")
        self.assertTrue(Path(j["previous_version"]).is_dir())  # previous version kept
        # user data never entered the build and is carried over unchanged
        self.assertEqual(j["carried_over"], ["data", ".env"])
        self.assertEqual((self.app / "data" / "jobs.sqlite3").read_text(), "user data")
        self.assertEqual((self.app / ".env").read_text(), "ADZUNA_APP_KEY=secret-value-123\n")
        argv_rec = Path(os.environ["FAKE_CLAUDE_ARGV"]).read_text()
        self.assertNotIn("secret-value-123", argv_rec)
        self.assertFalse((Path(j["previous_version"]) / "app.py").exists())
        self.assertIn("Outcome: enhanced", j["report"])  # read from docs/ENHANCE_REPORT.md
        self.assertEqual((self.app / "BUILD_SPEC.md").read_text(), "ORIGINAL SPEC\n")  # original spec kept
        spec = (self.app / "docs" / "ENHANCE_SPEC.md").read_text()
        self.assertTrue(spec.startswith("# Enhancement specification"))
        self.assertIn("Naukri/LinkedIn", spec)
        self.assertTrue((self.app / "docs" / "UAISES_TEST.md").exists())
        # backup taken before the build, without the venv
        with tarfile.open(j["backup"]) as t:
            names = t.getnames()
        self.assertIn("job-finder/data/jobs.sqlite3", names)
        self.assertIn("job-finder/BUILD_SPEC.md", names)
        self.assertFalse(any("/.venv" in n for n in names))
        self.assertNotIn("job-finder/app.py", names)
        self.assertGreaterEqual(j["backup_files"], 4)  # verified file count  # written by the build, so not in the earlier backup
        argv = json.loads(Path(os.environ["FAKE_CLAUDE_ARGV"]).read_text().splitlines()[-1])["argv"]
        prompt = argv[1]
        for need in ("ENHANCING an existing", "docs/ENHANCE_SPEC.md", "tools/coverage.sh", "Every existing test must still pass",
                     "Never delete or overwrite user data", "local fakes", "Do not commit", "docs/ENHANCE_REPORT.md",
                     "UI STANDARD (MANDATORY)"):
            self.assertIn(need, prompt)
        self.assertIn("Bash(tools/*:*)", argv)
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")

    def test_failed_enhancement_leaves_app_untouched(self):  # regression A11
        os.environ["FAKE_CLAUDE_MODE"] = "badtests"
        try:
            j = wait(self.mgr, self.mgr.start("x", enhance_answers(self.app), {})["id"])
        finally:
            os.environ["FAKE_CLAUDE_MODE"] = "ok"
        self.assertEqual(j["status"], "failed")
        self.assertFalse((self.app / "app.py").exists())
        self.assertFalse(j.get("applied"))
        self.assertTrue((Path(j["staging_dir"]) / "app.py").exists())  # attempted version kept for review

    def test_staging_never_contains_user_data(self):
        seen = {}
        orig = builder.gates.run_all

        def look(w, *a, **k):
            seen["data"] = sorted(p.name for p in (Path(w) / "data").iterdir())
            seen["env"] = (Path(w) / ".env").exists()
            return orig(w, *a, **k)
        builder.gates.run_all = look
        try:
            j = wait(self.mgr, self.mgr.start("x", enhance_answers(self.app), {})["id"])
        finally:
            builder.gates.run_all = orig
        self.assertEqual((seen["data"], seen["env"]), ([], False))
        self.assertEqual(j["status"], "succeeded", j.get("reasons"))

    def test_data_change_during_build_is_kept(self):
        orig = builder.gates.run_all

        def touch_then_verify(*a, **k):
            (self.app / "data" / "jobs.sqlite3").write_text("app wrote this during the build")
            return orig(*a, **k)
        builder.gates.run_all = touch_then_verify
        try:
            j = wait(self.mgr, self.mgr.start("x", enhance_answers(self.app), {})["id"])
        finally:
            builder.gates.run_all = orig
        self.assertEqual(j["status"], "succeeded", j.get("reasons"))  # data is carried over, so no conflict
        self.assertEqual((self.app / "data" / "jobs.sqlite3").read_text(), "app wrote this during the build")
        self.assertTrue((self.app / "app.py").exists())

    def test_user_change_during_build_blocks_apply(self):
        orig = builder.gates.run_all

        def touch_then_verify(*a, **k):
            (self.app / "README.md").write_text("user changed this during the build")
            return orig(*a, **k)
        builder.gates.run_all = touch_then_verify
        try:
            j = wait(self.mgr, self.mgr.start("x", enhance_answers(self.app), {})["id"])
        finally:
            builder.gates.run_all = orig
        self.assertEqual(j["status"], "blocked")
        self.assertFalse((self.app / "app.py").exists())
        self.assertEqual((self.app / "README.md").read_text(), "user changed this during the build")

    def test_symlinked_app_rejected(self):  # regression A17
        link = APPS / "linked"
        link.unlink(missing_ok=True)
        link.symlink_to(self.app)
        self.assertNotIn("linked", [a["name"] for a in builder.existing_apps()])
        link.unlink()

    def test_enhance_with_git_and_reuse(self):
        p = builder.enhance_prompt(builder.validate_spec("r", enhance_answers(self.app, git=True, reuse=[])))
        self.assertIn("Commit the change", p)
        self.assertIn("build the change here", p)


class StandardPathTests(unittest.TestCase):
    def test_env_then_config_then_bundled(self):
        cfg = helpers.TMP / "cfg.json"
        old_cfg, _old_env = builder.CONFIG_FILE, os.environ.pop("REQAN_X", None)
        builder.CONFIG_FILE = cfg
        try:
            bundled = builder.standard_path("REQAN_X", "uaises", "UNIVERSAL_AI_SOFTWARE_ENGINEERING_STANDARD.md")
            self.assertEqual(bundled, builder.PLUGIN_ROOT / "standards" / "UNIVERSAL_AI_SOFTWARE_ENGINEERING_STANDARD.md")
            self.assertTrue(bundled.exists())  # the published plugin ships both standards
            self.assertTrue((builder.PLUGIN_ROOT / "standards" / "UNIVERSAL_ENTERPRISE_UI_STANDARD.md").exists())
            cfg.write_text("not json")
            self.assertEqual(builder.standard_path("REQAN_X", "uaises", "b.md"), builder.PLUGIN_ROOT / "standards" / "b.md")
            cfg.write_text(json.dumps({"uaises": "~/mine.md"}))
            self.assertEqual(builder.standard_path("REQAN_X", "uaises", "b.md"), Path.home() / "mine.md")
            os.environ["REQAN_X"] = "/env/std.md"
            self.assertEqual(builder.standard_path("REQAN_X", "uaises", "b.md"), Path("/env/std.md"))
        finally:
            builder.CONFIG_FILE = old_cfg
            os.environ.pop("REQAN_X", None)


class EnhanceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.use_fixture_catalog()
        cls.gh = helpers.FakeGitHub("ok")
        helpers.use_github(cls.gh)
        cls.srv = server.make_server(0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.app = make_app("api-app")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.gh.close()

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=15)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Content-Type": "application/json", "X-ReqAn-Token": server.SESSION_TOKEN})
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b"null"))
        c.close()
        return out

    def test_apps_and_inputs_routes(self):
        st, r = self.req("GET", "/api/apps")
        self.assertEqual(st, 200)
        self.assertIn("api-app", [a["name"] for a in r["apps"]])
        st, r = self.req("POST", "/api/inputs", {"requirement": "Add auto apply", "target": str(self.app)})
        self.assertEqual((st, r["mode"]), (200, "enhance"))
        self.assertEqual(self.req("POST", "/api/inputs", {"requirement": "x", "target": "/etc"})[0], 400)
        self.assertEqual(self.req("POST", "/api/inputs", {"requirement": "x", "target": 5})[0], 400)
        self.assertEqual(self.req("POST", "/api/inputs", {"requirement": "x", "target": ""})[1]["mode"], "new")


if __name__ == "__main__":
    unittest.main()
