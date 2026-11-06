"""Reuse policy, state machine, verification gates, decision engine, redaction, and seeded fuzz/property tests."""
import json
import math
import random
import tempfile
import time
import unittest
from pathlib import Path

import helpers
from reqanalyzer import builder, decision, gates, obs, policy, reuse, sources
from reqanalyzer import lifecycle as L


class GithubUrlTests(unittest.TestCase):
    def test_accepts(self):
        u = policy.parse_github_url("https://github.com/acme/plugins/tree/HEAD/invoice")
        self.assertEqual((u["owner"], u["repo"], u["ref"], u["path"]), ("acme", "plugins", "HEAD", "invoice"))
        self.assertEqual(policy.parse_github_url("https://github.com/a/b.git")["clone_url"], "https://github.com/a/b")

    def test_rejects(self):
        for bad in ("http://github.com/a/b", "https://github.com.evil.example/a/b", "https://evil.example/github.com/a/b",
                    "https://user@github.com/a/b", "https://github.com:443/a/b", "https://github.com/a/b?x=1",
                    "https://github.com/a/b#x", "https://github.com/a", "https://github.com/a/b/blob/x",
                    "https://github.com/../b", "https://github.com/a/b/tree/x/../../c", "https://github.com/-a/b",
                    "https://github.com/a/b c", "", None, 5, "x" * 500, "https://github.com/a/b\nhttps://evil"):
            with self.subTest(bad=bad), self.assertRaises(policy.PolicyError):
                policy.parse_github_url(bad)

    def test_option_url_must_be_last_field(self):
        self.assertEqual(policy.reuse_option_url("GitHub · a/b · 1% · MIT · https://github.com/a/b")["repo"], "b")
        with self.assertRaises(policy.PolicyError):
            policy.reuse_option_url("GitHub · https://github.com/a/b · evil")

    def test_fuzz_never_accepts_non_github(self):
        rnd = random.Random(1234)
        alphabet = "abc/:.@?#%-_ \\\n\x00githubcom"
        for _ in range(3000):
            s = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 60)))
            if rnd.random() < 0.5:
                s = "https://github.com/" + s
            try:
                u = policy.parse_github_url(s)
            except policy.PolicyError:
                continue
            self.assertTrue(u["clone_url"].startswith("https://github.com/"))
            self.assertNotIn("..", u["clone_url"])
            self.assertRegex(u["clone_url"], r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


class LicenceTests(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(policy.licence_class("MIT")["reuse"], "allowed")
        self.assertEqual(policy.licence_class("GPL-3.0")["reuse"], "review")
        self.assertEqual(policy.licence_class("none")["reuse"], "learn-only")
        self.assertEqual(policy.licence_class(None)["reuse"], "learn-only")
        self.assertEqual(policy.licence_class("NOASSERTION")["reuse"], "review")
        self.assertEqual(policy.licence_class("CC-BY-NC-4.0")["reuse"], "learn-only")
        self.assertEqual(policy.licence_class("WTFPL")["reuse"], "review")

    def test_detect_and_reconcile(self):
        self.assertEqual(policy.detect_licence_text("MIT License\n\nPermission is hereby granted, free of charge, to"), "MIT")
        self.assertEqual(policy.detect_licence_text("GNU AFFERO GENERAL PUBLIC LICENSE ..."), "AGPL-3.0")
        self.assertIsNone(policy.detect_licence_text("all rights reserved"))
        self.assertEqual(policy.reconcile_licence("MIT", "GPL-3.0")["reuse"], "review")  # disagreement
        self.assertEqual(policy.reconcile_licence(None, "MIT")["reuse"], "allowed")
        self.assertEqual(policy.reconcile_licence("MIT", "MIT")["reuse"], "allowed")

    def test_maintenance(self):
        now = time.mktime(time.strptime("2026-11-06", "%Y-%m-%d"))
        self.assertEqual(policy.maintenance("2026-10-01", now=now)["state"], "active")
        self.assertEqual(policy.maintenance("2025-06-01", now=now)["state"], "stale")
        self.assertEqual(policy.maintenance("2020-01-01", now=now)["state"], "unmaintained")
        self.assertEqual(policy.maintenance("2026-10-01", archived=True)["state"], "archived")
        self.assertEqual(policy.maintenance(None)["state"], "unknown")
        self.assertEqual(policy.maintenance("garbage")["state"], "unknown")

    def test_auto_eligibility(self):
        good = {"url": "https://github.com/a/b", "coverage": 75, "licence": policy.licence_class("MIT"),
                "maintenance": {"state": "active"}, "compatibility": "pass", "evidence": {"confidence": 60}}
        self.assertEqual(policy.auto_reuse_eligible(good), (True, []))
        for change in ({"coverage": 49}, {"coverage": float("nan")}, {"licence": policy.licence_class("GPL-3.0")},
                       {"maintenance": {"state": "archived"}}, {"compatibility": "fail"}, {"evidence": {"confidence": 20}},
                       {"url": "https://gitlab.com/a/b"}, {"fork": True}):
            with self.subTest(change=change):
                ok, why = policy.auto_reuse_eligible({**good, **change})
                self.assertFalse(ok)
                self.assertTrue(why)


class ProvenanceTests(unittest.TestCase):
    def test_prepare_pins_and_excludes(self):
        w = Path(tempfile.mkdtemp())
        recs = reuse.prepare(w, ["GitHub · a/ok · 80% · MIT · https://github.com/a/ok",
                                 "GitHub · a/nolic · 80% · none · https://github.com/a/nolic"])
        self.assertTrue(recs[0]["cloned"])
        self.assertEqual(recs[0]["sha"], "0123456789abcdef0123456789abcdef01234567")
        self.assertFalse(recs[1]["cloned"])
        self.assertFalse((w / "upstream" / "a__nolic").exists())
        doc = (w / "docs" / "REUSE_PROVENANCE.md").read_text()
        self.assertIn("learn-only", doc)
        self.assertIn("upstream/", (w / ".gitignore").read_text())

    def test_gpl_clone_removed(self):
        def gpl(url, dest, workdir):
            r = helpers.fake_clone(url, dest, workdir)
            (dest / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE Version 3")
            return r
        old = reuse.clone_repo
        reuse.clone_repo = gpl
        try:
            w = Path(tempfile.mkdtemp())
            recs = reuse.prepare(w, ["Claude plugin · x · 50% · see repo · https://github.com/a/gpl"])
        finally:
            reuse.clone_repo = old
        self.assertFalse(recs[0]["cloned"])
        self.assertEqual(recs[0]["licence"]["class"], "strong-copyleft")
        self.assertFalse((w / "upstream" / "a__gpl").exists())


class LifecycleTests(unittest.TestCase):
    def test_happy_path_and_illegal(self):
        j = {"status": L.CREATED}
        for s in (L.VALIDATED, L.QUEUED, L.PREPARING, L.RUNNING, L.VERIFYING, L.SUCCEEDED):
            L.advance(j, s)
        self.assertEqual(len(j["transitions"]), 6)
        with self.assertRaises(L.TransitionError):
            L.advance(j, L.RUNNING)  # terminal
        with self.assertRaises(L.TransitionError):
            L.advance({"status": L.RUNNING}, L.SUCCEEDED)  # never skip verification

    def test_every_active_state_can_abort(self):
        for s in L.ACTIVE:
            for t in (L.FAILED, L.CANCELLED, L.INTERRUPTED):
                self.assertTrue(L.can(s, t), (s, t))

    def test_random_walks_stay_legal(self):
        rnd = random.Random(7)
        for _ in range(500):
            j = {"status": L.CREATED}
            while j["status"] not in L.TERMINAL:
                L.advance(j, rnd.choice(sorted(L.TRANSITIONS[j["status"]])))
            if j["status"] == L.SUCCEEDED:
                self.assertIn(L.VERIFYING, [t["from"] for t in j["transitions"]])

    def test_legacy_names(self):
        self.assertEqual(L.normalise("timed-out"), L.TIMED_OUT)
        self.assertTrue(L.is_active("running"))


class NumberFuzzTests(unittest.TestCase):
    def test_number_validation_property(self):
        rnd = random.Random(99)
        pool = [float("nan"), float("inf"), -float("inf"), True, False, None, [], {}, "1e9", "0x10", " 5 ", "5.5", "-1",
                "", "١٢", 1e308, -0.0, 0.49, 50.0001, 3]
        for _ in range(2000):
            v = rnd.choice(pool + [rnd.uniform(-100, 100), str(rnd.randint(-10, 100))])
            try:
                out = builder.number(v, "budget_usd", 0.5, 50)
            except builder.BuildError:
                continue
            self.assertTrue(math.isfinite(out) and 0.5 <= out <= 50, (v, out))
            self.assertNotIsInstance(v, bool)


class GateTests(unittest.TestCase):
    def proj(self):
        w = Path(tempfile.mkdtemp())
        for f in gates.REQUIRED_DOCS + ("docs/COMPLETION_REPORT.md",):
            (w / f).parent.mkdir(parents=True, exist_ok=True)
            (w / f).write_text("x")
        return w

    def test_required_syntax_secrets(self):
        w = self.proj()
        (w / "ok.py").write_text("x = 1\n")
        self.assertEqual(gates.g_required_files(w, False)["status"], gates.VERIFIED)
        self.assertEqual(gates.g_syntax(w)["status"], gates.VERIFIED)
        (w / "bad.py").write_text("def (:\n")
        self.assertEqual(gates.g_syntax(w)["status"], gates.FAILED)
        self.assertEqual(gates.g_secrets(w)["status"], gates.VERIFIED)
        (w / "k.txt").write_text("token ghp_" + "A" * 36)
        g = gates.g_secrets(w)
        self.assertEqual(g["status"], gates.FAILED)
        self.assertNotIn("A" * 36, json.dumps(g))  # findings never echo the secret
        (w / "README.md").unlink()
        self.assertEqual(gates.g_required_files(w, False)["status"], gates.FAILED)

    def test_dependencies_and_sbom(self):
        w = self.proj()
        (w / "requirements.txt").write_text("flask==3.0.3\nrequests>=2\n# c\n-r other.txt\n")
        (w / "package.json").write_text(json.dumps({"dependencies": {"left-pad": "1.3.0", "x": "^2"}}))
        deps = gates.dependencies(w)
        self.assertIn({"ecosystem": "PyPI", "name": "flask", "version": "3.0.3", "source": "requirements.txt"}, deps)
        g, _ = gates.g_sbom(w, "app")
        self.assertEqual(g["status"], gates.NOT_VERIFIED)  # unpinned requests/x
        bom = json.loads((w / "docs" / "sbom.cdx.json").read_text())
        self.assertEqual((bom["bomFormat"], bom["specVersion"]), ("CycloneDX", "1.5"))
        self.assertIn("pkg:pypi/flask@3.0.3", [c["purl"] for c in bom["components"]])

    def test_osv_offline_is_not_verified(self):
        st, _ = gates.osv_check([{"ecosystem": "PyPI", "name": "flask", "version": "3.0.3"}], timeout=1)
        self.assertEqual(st, gates.NOT_VERIFIED)
        self.assertEqual(gates.osv_check([])[0], gates.VERIFIED)

    def test_test_output_parsing(self):
        p = gates.parse_test_output
        self.assertEqual(p("Ran 5 tests in 0.1s\n\nOK"), {"passed": 5, "failed": 0, "skipped": 0})
        self.assertEqual(p("Ran 5 tests\nFAILED (failures=1, errors=1)"), {"passed": 3, "failed": 2, "skipped": 0})
        self.assertEqual(p("Ran 92 tests in 13s\n\nOK (skipped=6)"), {"passed": 86, "failed": 0, "skipped": 6})  # regression
        self.assertEqual(p("Ran 9 tests\nFAILED (errors=1, skipped=2, expected failures=1)"), {"passed": 5, "failed": 1, "skipped": 3})
        self.assertEqual(p("== 7 passed, 2 failed, 3 skipped in 1s =="), {"passed": 7, "failed": 2, "skipped": 3})

    def test_decide(self):
        g = lambda st, m=True: {"name": "g", "mandatory": m, "status": st, "detail": "d"}
        self.assertEqual(gates.decide([g(gates.VERIFIED), g(gates.NA), g(gates.FAILED, False)])[0], L.SUCCEEDED)
        self.assertEqual(gates.decide([g(gates.VERIFIED), g(gates.NOT_VERIFIED)])[0], L.PARTIALLY_COMPLETED)
        self.assertEqual(gates.decide([g(gates.BLOCKED), g(gates.FAILED)])[0], L.FAILED)

    def test_regression_gate(self):
        base = {"status": "passed", "passed": 10, "failed": 0}
        self.assertEqual(gates.g_regression(base, {"status": "passed", "passed": 12})["status"], gates.VERIFIED)
        self.assertEqual(gates.g_regression(base, {"status": "passed", "passed": 9})["status"], gates.FAILED)
        self.assertEqual(gates.g_regression(base, {"status": "failed", "passed": 10, "failed": 1})["status"], gates.FAILED)
        self.assertEqual(gates.g_regression(None, {"status": "passed", "passed": 1})["status"], gates.NOT_VERIFIED)


class DecisionTests(unittest.TestCase):
    def cand(self, **kw):
        c = {"name": "a/b", "id": "github:a/b", "url": "https://github.com/a/b", "coverage": 85, "closeness": 85,
             "missing": [], "licence": policy.licence_class("MIT"), "maintenance": {"state": "active"},
             "compatibility": "pass", "evidence": {"confidence": 70}, "recommendation": "reuse"}
        c.update(kw)
        return c

    def test_strong_match_reuses(self):
        d = decision.decide({"concepts": list("abcdef"), "github": [self.cand()]})
        self.assertEqual(d["recommendation"], "reuse")
        self.assertTrue(d["assumptions"] and d["sensitivity"])

    def test_no_licence_cannot_be_reused(self):
        d = decision.decide({"concepts": list("abcdef"), "github": [self.cand(licence=policy.licence_class("none"))]})
        self.assertEqual(d["recommendation"], "insufficient evidence")
        self.assertFalse(d["options"][0]["copyable"])

    def test_weak_matches_build_new(self):
        self.assertEqual(decision.decide({"concepts": ["a"], "github": [self.cand(coverage=10)]})["recommendation"], "build new")

    def test_many_missing_capabilities_build_new(self):
        c = self.cand(coverage=55, missing=list("abcdefghij"), compatibility="unknown", evidence={"confidence": 40},
                      recommendation="extend")
        self.assertEqual(decision.decide({"concepts": list("abcdefghijkl"), "github": [c]})["recommendation"], "build new")

    def test_capability_estimate_diminishes(self):
        self.assertEqual(decision.capabilities(0), 1)
        self.assertEqual(decision.capabilities(6), 6)
        self.assertEqual(decision.capabilities(59), 25.0 if 8 + 51 / 3 > 25 else round(8 + 51 / 3, 1))
        self.assertLess(decision.decide({"concepts": list(range(51))})["build_new"]["high"], 2 * 25 + 4 + 0.01)

    def test_report_and_outcomes(self):
        md = decision.report_markdown({"created_at": time.time(), "result": {"requirement": "x", "concepts": ["a"],
                                                                               "github": [self.cand()]}})
        self.assertIn("Recommendation:", md)
        self.assertIn("uncalibrated", md)
        f = Path(tempfile.mkdtemp()) / "o.jsonl"
        f.write_text("\n".join(json.dumps({"reuse_count": i % 2, "minutes": i, "cost_usd": 1.0, "status": "succeeded"})
                               for i in range(10)) + "\nnot json\n")
        s = decision.outcome_summary(f)
        self.assertEqual((s["with_reuse"]["builds"], s["without_reuse"]["builds"]), (5, 5))
        self.assertEqual(decision.outcome_summary(Path("/nonexistent"))["with_reuse"]["builds"], 0)


class RedactionTests(unittest.TestCase):
    def test_redacts(self):
        for secret in ("sk-ant-api03-" + "x" * 30, "ghp_" + "a" * 36, "AKIAABCDEFGHIJKLMNOP", "xoxb-1234567890-abc",
                       "Authorization: Bearer abc.def.ghi", "password=hunter2hunter2",
                       "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----"):
            with self.subTest(secret=secret[:12]):
                out = obs.redact(f"prefix {secret} suffix")
                self.assertIn("REDACTED", out)
                self.assertNotIn(secret.split()[-1][-8:], out)
        self.assertEqual(obs.redact_obj({"token": "abc", "n": [{"x": "ghp_" + "b" * 36}]})["token"], "[REDACTED]")


class CacheTests(unittest.TestCase):
    def test_bounded_lru_ttl(self):
        c = sources.TTLCache(maxsize=2, ttl=60)
        c.put("a", 1)
        c.put("b", 2)
        c.get("a")
        c.put("c", 3)
        self.assertIsNone(c.get("b"))  # least recently used evicted
        self.assertEqual(c.get("a")[1], 1)
        c2 = sources.TTLCache(ttl=0)
        c2.put("x", 1)
        self.assertIsNone(c2.get("x"))

    def test_api_scheme_guard(self):  # regression A19
        for bad in ("file:///etc/passwd", "ftp://x", "http://evil.example"):
            with self.assertRaises(ValueError):
                sources.safe_base(bad)
        self.assertEqual(sources.safe_base("https://api.github.com/"), "https://api.github.com")


if __name__ == "__main__":
    unittest.main()
