"""Integration tests: real file catalogs + a fake GitHub HTTP API (no network)."""
import json
import os
import unittest
from pathlib import Path

import helpers
from reqanalyzer import engine, sources

REQ = "Self-hosted invoicing app with recurring billing, PDF invoices and Stripe payments"


class CatalogTests(unittest.TestCase):
    def test_loads_cache_and_marketplace_dedup(self):
        plugins, errors = sources.load_claude_plugins(helpers.FIXTURES / "plugins")
        names = [p["name"] for p in plugins]
        self.assertEqual(errors, [])
        self.assertEqual(names.count("invoice-maker"), 1)
        self.assertIn("note-taker", names)
        nt = next(p for p in plugins if p["name"] == "note-taker")
        self.assertEqual(nt["url"], "https://github.com/acme/notes")
        km = next(p for p in plugins if p["name"] == "kanban-board")
        self.assertEqual(km["url"], "https://github.com/acme/plugins/tree/HEAD/kanban")

    def test_same_name_different_repos_both_kept(self):  # regression A9
        import tempfile
        d = Path(tempfile.mkdtemp())
        for m, url in (("a", "https://github.com/one/pdf"), ("b", "https://github.com/two/pdf")):
            (d / "marketplaces" / m / ".claude-plugin").mkdir(parents=True)
            (d / "marketplaces" / m / ".claude-plugin" / "marketplace.json").write_text(
                json.dumps({"plugins": [{"name": "pdf", "description": m, "homepage": url}]}))
        plugins, _ = sources.load_claude_plugins(d)
        self.assertEqual(sorted(p["id"] for p in plugins), ["marketplace:a/pdf", "marketplace:b/pdf"])

    def test_missing_catalog_reports_error(self):
        plugins, errors = sources.load_claude_plugins(helpers.FIXTURES / "does-not-exist")
        self.assertEqual(plugins, [])
        self.assertTrue(any("not found" in e for e in errors))

    def test_malformed_catalog_reports_errors_not_crash(self):
        plugins, errors = sources.load_claude_plugins(helpers.FIXTURES / "broken")
        self.assertEqual(plugins, [])
        self.assertEqual(len(errors), 2)


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        helpers.use_fixture_catalog()
        self.gh = helpers.FakeGitHub("ok")
        helpers.use_github(self.gh)

    def tearDown(self):
        self.gh.close()

    def test_ranks_real_match_first(self):
        r = engine.analyze(REQ)
        self.assertEqual(r["claude_plugins"][0]["name"], "invoice-maker")
        self.assertEqual(r["github"][0]["name"], "acme/stripe-invoices")
        self.assertGreaterEqual(r["github"][0]["closeness"], 70)
        self.assertEqual(r["github_status"], "ok")
        self.assertTrue(r["verdict"].startswith("Reuse"))
        self.assertEqual(r["best"]["name"], "acme/stripe-invoices")

    def test_unrelated_plugins_are_excluded(self):
        names = [p["name"] for p in engine.analyze(REQ)["claude_plugins"]]
        self.assertNotIn("weather-skill", names)

    def test_padded_description_does_not_outrank(self):  # regression: pasted-document "descriptions"
        r = engine.analyze(REQ)
        rank = {x["name"]: i for i, x in enumerate(r["github"])}
        self.assertLess(rank["acme/stripe-invoices"], rank["spam/whitepaper"])

    def test_repo_record_fields(self):
        rec = next(x for x in engine.analyze(REQ)["github"] if x["name"] == "acme/claude-invoice-plugin")
        self.assertTrue(rec["is_claude_plugin"])
        self.assertTrue(rec["archived"])
        self.assertEqual((rec["license"], rec["updated"], rec["language"]), ("none", "", ""))

    def test_queries_are_bounded_and_scoped(self):
        r = engine.analyze(REQ)
        self.assertLessEqual(len(self.gh.queries), engine.MAX_GITHUB_QUERIES)
        self.assertTrue(all("in%3Aname%2Cdescription%2Ctopics" in q for q in self.gh.queries))

    def test_queries_use_surface_words(self):
        engine.analyze("recurring subscriptions", github=True)
        self.assertTrue(any("recurring" in q for q in self.gh.queries), self.gh.queries)
        self.assertFalse(any("recurr+" in q or q.endswith("recurr") for q in self.gh.queries))

    def test_results_cached(self):
        engine.analyze(REQ)
        n = len(self.gh.queries)
        engine.analyze(REQ)
        self.assertEqual(len(self.gh.queries), n)

    def test_no_github(self):
        r = engine.analyze(REQ, github=False)
        self.assertEqual((r["github"], r["github_status"], self.gh.queries), ([], "skipped", []))

    def test_token_sent_when_configured(self):
        os.environ["GITHUB_TOKEN"] = "ghp_" + "a" * 36
        try:
            helpers.use_github(self.gh)
            engine.analyze(REQ)
            self.assertEqual(self.gh.auth, "Bearer ghp_" + "a" * 36)
            self.assertNotIn("ghp_", str(engine.analyze(REQ)))  # never echoed back
        finally:
            del os.environ["GITHUB_TOKEN"]
            helpers.use_github(self.gh)


class GitHubFailureTests(unittest.TestCase):
    def setUp(self):
        helpers.use_fixture_catalog()

    def _run(self, mode):
        gh = helpers.FakeGitHub(mode)
        helpers.use_github(gh)
        try:
            return engine.analyze(REQ), gh
        finally:
            gh.close()

    def test_rate_limited_is_visible_and_stops(self):
        r, gh = self._run("ratelimit")
        self.assertEqual(r["github_status"], "rate-limited")
        self.assertEqual(len(gh.queries), 1)
        self.assertTrue(any("rate limited" in e for e in r["errors"]))
        self.assertEqual(r["github"], [])  # no synthetic fallback results
        self.assertEqual(r["claude_plugins"][0]["name"], "invoice-maker")  # plugins still work

    def test_server_error_reported(self):
        r, _ = self._run("error")
        self.assertEqual(r["github_status"], "failed")
        self.assertTrue(any("HTTP 500" in e for e in r["errors"]))

    def test_unreachable_reported(self):
        sources.GITHUB_API = "http://127.0.0.1:9"
        sources._cache.clear()
        r = engine.analyze(REQ)
        self.assertEqual(r["github_status"], "failed")
        self.assertTrue(any("unreachable" in e for e in r["errors"]))

    def test_empty_results(self):
        r, _ = self._run("empty")
        self.assertEqual((r["github_status"], r["github"]), ("ok", []))


class ValidationTests(unittest.TestCase):
    def test_rejects_bad_input(self):
        for req, kw in [("", None), ("   ", None), (None, None), (123, None), ("x" * 5001, None),
                        ("ok", "notalist"), ("ok", [1]), ("ok", ["k"] * 21), ("ok", ["x" * 101])]:
            with self.subTest(req=str(req)[:10], kw=str(kw)[:10]):
                with self.assertRaises(engine.InputError):
                    engine.analyze(req, kw, github=False)

    def test_top_is_clamped(self):
        helpers.use_fixture_catalog()
        self.assertLessEqual(len(engine.analyze(REQ, top=0, github=False)["claude_plugins"]), 1)

    def test_stopword_only_requirement(self):
        helpers.use_fixture_catalog()
        r = engine.analyze("I want a new app", github=True)
        self.assertEqual((r["concepts"], r["github_status"], r["best"]), ([], "skipped", None))
        self.assertTrue(r["verdict"].startswith("Build new"))


if __name__ == "__main__":
    unittest.main()
