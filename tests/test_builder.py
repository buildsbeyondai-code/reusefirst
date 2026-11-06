"""Build tab: inputs, validation, prompt contents and the background build lifecycle (fake claude CLI)."""
import http.client
import json
import os
import threading
import time
import unittest
from pathlib import Path

import helpers
from reqanalyzer import builder, server

ANALYSIS = {
    "github": [
        {"name": "acme/stripe-invoices", "closeness": 82, "license": "MIT", "url": "https://github.com/acme/stripe-invoices", "description": "x"},
        {"name": "acme/billing", "closeness": 41, "license": "none", "url": "https://github.com/acme/billing", "description": "x"},
        {"name": "acme/weak", "closeness": 12, "license": "MIT", "url": "https://github.com/acme/weak", "description": "x"},
    ],
    "claude_plugins": [
        {"name": "invoice-maker", "closeness": 55, "url": "https://github.com/acme/plugins/tree/HEAD/invoice", "description": "x"},
        {"name": "no-url-plugin", "closeness": 50, "url": "", "description": "x"},
    ],
}


def answers(tmp_name, **over):
    a = {"app_name": "Invoice Hub", "output_dir": str(helpers.TMP / "apps" / tmp_name), "users": "me",
         "platforms": "WSL", "journeys": "create invoice", "must_have": "Create invoice", "acceptance": "Given x when y then z",
         "reuse": ["GitHub · acme/stripe-invoices · 82% · MIT · https://github.com/acme/stripe-invoices",
                   "Claude plugin · invoice-maker · 55% · see repo · https://github.com/acme/plugins/tree/HEAD/invoice"],
         "git": True, "budget_usd": 3, "max_minutes": 5, "model": "default", "port": 5071}
    a.update(over)
    return a


def wait(mgr, job_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        j = mgr.get(job_id)
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.1)
    raise AssertionError("build did not finish")


class InputsTests(unittest.TestCase):
    def tearDown(self):
        os.environ["FAKE_CLAUDE_MODE"] = "ok"

    def test_standard_fields_cover_uaises_section_2(self):
        ids = {f["id"] for f in builder.base_fields("invoice app", None)}
        for need in ("users", "platforms", "journeys", "must_have", "should_have", "optional", "acceptance",
                     "integrations", "nfr_performance", "nfr_reliability", "nfr_resources", "nfr_security",
                     "nfr_accessibility", "offline", "installation", "risk"):
            self.assertIn(need, ids)
        self.assertTrue(set(builder.REQUIRED_FIELDS) <= ids)

    def test_reuse_preselects_closest(self):
        opts, picked = builder.reuse_candidates(ANALYSIS)
        self.assertEqual(len(opts), 4)  # plugin without a GitHub URL is not offered
        self.assertEqual([p.split(" · ")[1] for p in picked], ["acme/stripe-invoices", "acme/billing", "invoice-maker"])

    def test_reuse_top_match_always_ticked_even_if_weak(self):
        _, picked = builder.reuse_candidates({"github": [ANALYSIS["github"][2]], "claude_plugins": []})
        self.assertEqual(len(picked), 1)

    def test_claude_prefill_is_sanitised(self):
        r = builder.required_inputs("invoice app", ANALYSIS)
        by = {f["id"]: f for f in r["fields"]}
        self.assertEqual(r["ai_status"], "ok")
        self.assertEqual(by["app_name"]["default"], "Invoice Hub")
        self.assertTrue(by["output_dir"]["default"].endswith("/invoice-hub"))
        self.assertEqual(by["data_storage"]["default"], "SQLite")
        self.assertNotEqual(by["auth"]["default"], "NOT AN OPTION")  # invalid select value ignored
        self.assertNotIn("evil_field", by)
        self.assertNotIn("stripe_api_key", by)  # never ask for secrets
        self.assertNotIn("bad", by)
        self.assertNotIn("server_port", by)  # duplicates the standard port field
        self.assertIn("report_format", by)  # "port" inside a word is not a duplicate
        self.assertEqual(by["currency"]["default"], "INR")
        self.assertEqual(by["tax_rate"]["default"], 18)
        self.assertIs(by["pdf_logo"]["default"], True)
        self.assertEqual(by["tone"]["type"], "text")  # select with no options degrades to text
        self.assertEqual(r["fields"][-1]["id"], "max_minutes")  # run limits stay last

    def test_uaises_section_2_is_sent_to_claude(self):
        Path(os.environ["FAKE_CLAUDE_ARGV"]).unlink(missing_ok=True)
        builder.required_inputs("invoice app", None)
        call = json.loads(Path(os.environ["FAKE_CLAUDE_ARGV"]).read_text().splitlines()[-1])
        prompt = call["argv"][call["argv"].index("-p") + 1]
        self.assertIn("Requirements and Acceptance Criteria", prompt)
        self.assertNotIn("Architecture Before Implementation", prompt)
        self.assertIn("UEUIS", prompt)
        r = builder.required_inputs("invoice app", None)
        self.assertTrue(r["ui_standard_found"])
        self.assertTrue(r["ui_standard"].endswith("UEUIS_TEST.md"))
        self.assertIn("--tools", call["argv"])

    def test_claude_failure_falls_back_visibly(self):
        for mode in ("inputs-error", "inputs-garbage"):
            os.environ["FAKE_CLAUDE_MODE"] = mode
            r = builder.required_inputs("invoice app", None)
            self.assertEqual(r["ai_status"], "failed")
            self.assertTrue(r["ai_error"])
            self.assertTrue(all(f["source"] == "standard" for f in r["fields"]))

    def test_missing_cli(self):
        old = os.environ.pop("REQAN_CLAUDE_BIN")
        try:
            os.environ["PATH"], path = "/nonexistent", os.environ["PATH"]
            orig_home = builder.Path.home
            builder.Path.home = staticmethod(lambda: Path("/nonexistent"))
            self.assertEqual(builder.required_inputs("x", None)["ai_status"], "failed")
        finally:
            builder.Path.home = orig_home
            os.environ["PATH"] = path
            os.environ["REQAN_CLAUDE_BIN"] = old


class SpecTests(unittest.TestCase):
    def test_rejects(self):
        cases = [
            ("", answers("a")),
            ("req", "notadict"),
            ("req", answers("a", must_have="")),
            ("req", answers("a", acceptance="  ")),
            ("req", answers("a", output_dir="/etc/evil")),
            ("req", answers("a", output_dir=str(helpers.TMP / ".." / "escape"))),
            ("req", answers("a", reuse=["no url here"])),
            ("req", answers("a", reuse=["x"] * 21)),
            ("req", answers("a", model="gpt")),
            ("req", answers("a", ui_level="Whatever")),
            ("req", answers("a", port=5060)),  # regression: browser-blocked (ERR_UNSAFE_PORT)
            ("req", answers("a", port=5057)),
            ("req", answers("a", port=80)),
            ("req", answers("a", port="abc")),
            ("req", answers("a", budget_usd="lots")),
            ("req", {**answers("a"), "Bad Key": 1}),
            ("req", answers("a", notes={"nested": 1})),
        ]
        for req, a in cases:
            with self.subTest(a=str(a)[:60]):
                with self.assertRaises(builder.BuildError):
                    builder.validate_spec(req, a)

    def test_rejects_non_empty_folder(self):
        d = helpers.TMP / "apps" / "full"
        d.mkdir(parents=True, exist_ok=True)
        (d / "x").write_text("x")
        with self.assertRaises(builder.BuildError):
            builder.validate_spec("req", answers("full"))

    def test_default_port_is_browser_safe(self):
        p = builder.free_port()
        self.assertNotIn(p, builder.BROWSER_UNSAFE_PORTS | builder.RESERVED_PORTS)
        self.assertNotIn(builder.free_port(5060), builder.BROWSER_UNSAFE_PORTS)

    def test_clamps_limits(self):
        a = builder.validate_spec("req", answers("c", budget_usd=999, max_minutes=0))
        self.assertEqual((a["budget_usd"], a["max_minutes"]), (50.0, 2))

    def test_prompt_contents(self):
        a = builder.validate_spec("req", answers("p"))
        p = builder.build_prompt(a)
        self.assertIn("NON-INTERACTIVELY", p)
        self.assertIn("MANDATORY", p)
        self.assertIn("git clone --depth 1 https://github.com/acme/stripe-invoices upstream/stripe-invoices", p)
        self.assertIn("git clone --depth 1 https://github.com/acme/plugins upstream/plugins (plugin lives in subfolder invoice)", p)
        self.assertIn("docs/REUSE.md", p)
        self.assertIn("127.0.0.1:5071", p)
        self.assertIn("no reuse", builder.reuse_instructions([]).lower() + " no reuse")
        # every build follows the UI standard; default level Enterprise, the §20 UI gate table is required
        self.assertIn("UI STANDARD (MANDATORY): docs/UEUIS_TEST.md", p)
        self.assertIn("Enterprise (WCAG 2.2 AA", p)
        self.assertIn("WCAG 2.2 AA", p)
        self.assertIn("docs/UI_STATES.md", p)
        self.assertIn("UEUIS §20 UI gate table", p)
        self.assertIn("§8.14 the top-20 professional polish checklist", p)
        self.assertIn("VISIBLY different in the header", p)
        self.assertIn("§8.15 button restraint", p)
        self.assertIn("§8.16 a named palette per theme", p)
        self.assertIn("§8.17 enterprise restraint (NO gradients", p)
        self.assertIn("§8.18 a remembered", p)
        self.assertIn("§8.19 focused pages", p)
        self.assertIn("§9.1 laptop density", p)

    def test_ui_standard_scales_to_apps_without_a_ui(self):
        for over in ({"app_type": "CLI tool"}, {"ui_theme": "No UI"}):
            p = builder.build_prompt(builder.validate_spec("req", answers("n", **over)))
            self.assertIn("UI STANDARD (MANDATORY)", p)
            self.assertIn("no graphical UI", p)
            self.assertNotIn("docs/UI_STATES.md", p)
        p = builder.build_prompt(builder.validate_spec("req", answers("r", ui_level=builder.UI_LEVELS[2])))
        self.assertIn("Regulated (Enterprise + domain law)", p)

    def test_ui_level_field_and_inputs_prompt(self):
        fields = {f["id"]: f for f in builder.base_fields("invoice app", None)}
        self.assertEqual(fields["ui_level"]["default"], builder.UI_LEVELS[0])
        self.assertIn("WCAG 2.2 AA", fields["nfr_accessibility"]["default"])

    def test_allowlist_is_safe(self):
        joined = " ".join(builder.BUILD_TOOLS)
        for bad in ("Bash(rm", "Bash(sudo", "Bash(*", "Bash(curl:", "Bash(git push", "Bash(git -c", "Bash(git -C"):
            self.assertNotIn(bad, joined)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        os.environ["FAKE_CLAUDE_MODE"] = "ok"
        self.mgr = builder.BuildManager(helpers.TMP / f"state-{self._testMethodName}")
        Path(os.environ["FAKE_CLAUDE_ARGV"]).unlink(missing_ok=True)

    def tearDown(self):
        os.environ["FAKE_CLAUDE_MODE"] = "ok"

    def test_success(self):
        job = self.mgr.start("Invoice app", answers("ok1"), {"must_have": "MUST-have features"})
        j = wait(self.mgr, job["id"])
        out = Path(j["output_dir"])
        self.assertEqual(j["status"], "succeeded")
        self.assertEqual((j["cost_usd"], j["denials"], j["result"]), (1.23, 1, "Built Invoice Hub"))
        self.assertTrue(j["has_run_sh"] and j["has_reuse_doc"])
        self.assertIn("Outcome: built", j["report"])
        spec = (out / "BUILD_SPEC.md").read_text()
        self.assertIn("### MUST-have features", spec)
        self.assertIn("- GitHub · acme/stripe-invoices", spec)
        self.assertNotIn("budget_usd", spec)
        self.assertEqual((out / "docs" / "UAISES_TEST.md").read_text(), (helpers.FIXTURES / "UAISES_TEST.md").read_text())
        self.assertEqual((out / "docs" / "UEUIS_TEST.md").read_text(), (helpers.FIXTURES / "UEUIS_TEST.md").read_text())
        kinds = [e["kind"] for e in j["events"]]
        self.assertIn("tool", kinds)
        self.assertIn("error", kinds)
        self.assertTrue(any("1/2 tasks done" in e["text"] for e in j["events"]))
        argv = json.loads(Path(os.environ["FAKE_CLAUDE_ARGV"]).read_text().splitlines()[-1])
        self.assertEqual(argv["cwd"], str(out))
        a = argv["argv"]
        self.assertEqual(a[a.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(a[a.index("--max-budget-usd") + 1], "3.00")
        self.assertNotIn("--model", a)
        self.assertIn(f"Bash({out}/.venv/bin/*:*)", a)  # regression: absolute venv path was refused in a real build
        # persisted
        self.assertEqual(json.loads((self.mgr.dir / j["id"] / "job.json").read_text())["status"], "succeeded")
        self.assertTrue((self.mgr.dir / j["id"] / "stream.jsonl").stat().st_size > 0)

    def test_since_returns_only_new_events(self):
        j = wait(self.mgr, self.mgr.start("r", answers("since"))["id"])
        n = j["event_count"]
        self.assertEqual(self.mgr.get(j["id"], n)["events"], [])
        self.assertEqual(len(self.mgr.get(j["id"], n - 1)["events"]), 1)

    def test_failure_and_budget(self):
        os.environ["FAKE_CLAUDE_MODE"] = "fail"
        j = wait(self.mgr, self.mgr.start("r", answers("fail1"))["id"])
        self.assertEqual(j["status"], "failed")
        self.assertIn("spending cap", j["error"])

    def test_crash(self):
        os.environ["FAKE_CLAUDE_MODE"] = "crash"
        j = wait(self.mgr, self.mgr.start("r", answers("crash1"))["id"])
        self.assertEqual(j["status"], "failed")
        self.assertIn("code 3", j["error"])
        self.assertTrue(any(e["kind"] == "stderr" for e in j["events"]))

    def test_one_at_a_time_and_cancel(self):
        os.environ["FAKE_CLAUDE_MODE"] = "slow"
        job = self.mgr.start("r", answers("slow1", model="sonnet"))
        time.sleep(0.8)
        with self.assertRaises(builder.BuildError) as cm:
            self.mgr.start("r", answers("slow2"))
        self.assertIn("still running", str(cm.exception))
        self.assertTrue(self.mgr.cancel(job["id"]))
        j = wait(self.mgr, job["id"])
        self.assertEqual(j["status"], "cancelled")
        self.assertFalse(self.mgr.cancel(job["id"]))

    def test_timeout(self):
        os.environ["FAKE_CLAUDE_MODE"] = "slow"
        a = builder.validate_spec("r", answers("to1"))
        job = {"id": "t-timeout", "app_name": "x", "output_dir": a["output_dir"], "status": "queued", "created_at": time.time(),
               "started_at": None, "finished_at": None, "events": []}
        self.mgr.jobs[job["id"]] = job
        Path(a["output_dir"]).mkdir(parents=True)
        (self.mgr.dir / job["id"]).mkdir()
        self.mgr._run(job, [os.environ["REQAN_CLAUDE_BIN"], "-p", "x", "--output-format", "stream-json"], Path(a["output_dir"]), 1)
        self.assertEqual(job["status"], "timed-out")

    def test_restart_marks_interrupted(self):
        os.environ["FAKE_CLAUDE_MODE"] = "slow"
        job = self.mgr.start("r", answers("int1"))
        time.sleep(0.5)
        again = builder.BuildManager(self.mgr.dir.parent)
        self.assertEqual(again.get(job["id"])["status"], "interrupted")
        self.mgr.cancel(job["id"])

    def test_missing_standard_refuses(self):
        old = builder.UAISES
        builder.UAISES = Path("/nonexistent/UAISES.md")
        try:
            with self.assertRaises(builder.BuildError) as cm:
                self.mgr.start("r", answers("nostd"))
            self.assertIn("UAISES", str(cm.exception))
        finally:
            builder.UAISES = old

    def test_missing_ui_standard_refuses(self):
        old = builder.UI_STANDARD
        builder.UI_STANDARD = Path("/nonexistent/UEUIS.md")
        try:
            with self.assertRaises(builder.BuildError) as cm:
                self.mgr.start("r", answers("noui"))
            self.assertIn("UEUIS", str(cm.exception))
        finally:
            builder.UI_STANDARD = old

    def test_launch(self):
        j = wait(self.mgr, self.mgr.start("r", answers("launch1"))["id"])
        r = self.mgr.launch(j["id"])
        self.assertEqual(r["url"], "http://127.0.0.1:5071/")
        os.kill(r["pid"], 15)
        with self.assertRaises(builder.BuildError):
            self.mgr.launch("nope")

    def test_git_identity_env(self):
        os.environ["REQAN_GIT_NAME"], os.environ["REQAN_GIT_EMAIL"] = "Tester", "t@example.com"
        try:
            env = builder.git_env()
            self.assertEqual((env["GIT_AUTHOR_NAME"], env["GIT_COMMITTER_EMAIL"]), ("Tester", "t@example.com"))
        finally:
            del os.environ["REQAN_GIT_NAME"], os.environ["REQAN_GIT_EMAIL"]
        self.assertTrue(builder.git_env()["GIT_AUTHOR_NAME"])

    def test_summarize(self):
        self.assertEqual(builder.summarize({"type": "rate_limit_event"}), [])
        self.assertEqual(builder.summarize({"type": "result", "subtype": "success", "num_turns": 2, "total_cost_usd": 0.5}),
                         [("done", "success · 2 turns · $0.50")])


class BuildApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.use_fixture_catalog()
        cls.gh = helpers.FakeGitHub("ok")
        helpers.use_github(cls.gh)
        server._builds = builder.BuildManager(helpers.TMP / "state-api")
        cls.srv = server.make_server(0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.gh.close()
        server._builds = None

    def req(self, method, path, body=None, token=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        h = {"Content-Type": "application/json"}
        if token:
            h["X-ReqAn-Token"] = server.SESSION_TOKEN
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b"null"))
        c.close()
        return out

    def test_session_and_inputs(self):
        st, s = self.req("GET", "/api/session")
        self.assertEqual((st, s["token"], s["claude_cli"]), (200, server.SESSION_TOKEN, True))
        st, r = self.req("POST", "/api/inputs", {"requirement": "Stripe invoicing with PDF invoices"})
        self.assertEqual(st, 200)
        reuse = next(f for f in r["fields"] if f["id"] == "reuse")
        self.assertTrue(reuse["default"])  # closest projects pre-ticked
        self.assertTrue(all("https://github.com/" in o for o in reuse["options"]))
        self.assertEqual(self.req("POST", "/api/inputs", {"requirement": ""})[0], 400)

    def test_build_requires_token(self):
        st, r = self.req("POST", "/api/build", {"requirement": "x", "answers": answers("api0")}, token=False)
        self.assertEqual(st, 403)
        self.assertEqual(self.req("POST", "/api/builds/x/cancel", {}, token=False)[0], 403)

    def test_build_flow(self):
        st, job = self.req("POST", "/api/build", {"requirement": "Invoice app", "answers": answers("api1"),
                                                   "labels": {"must_have": "MUST"}})
        self.assertEqual(st, 202)
        end = time.time() + 20
        while time.time() < end:
            st, j = self.req("GET", f"/api/builds/{job['id']}?since=0")
            if j["status"] == "succeeded":
                break
            time.sleep(0.2)
        self.assertEqual(j["status"], "succeeded")
        self.assertIn(job["id"], [b["id"] for b in self.req("GET", "/api/builds")[1]["builds"]])
        self.assertEqual(self.req("GET", "/api/builds/nope")[0], 404)
        self.assertEqual(self.req("POST", "/api/builds/nope/cancel", {})[0], 409)
        self.assertEqual(self.req("POST", "/api/build", {"requirement": "x", "answers": answers("api1")})[0], 400)  # not empty now


if __name__ == "__main__":
    unittest.main()
