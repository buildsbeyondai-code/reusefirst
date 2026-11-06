import unittest

import helpers  # noqa: F401  (sets import path)
from reqanalyzer import textscore as ts

IDF = lambda t: 1.0  # noqa: E731  uniform weights make expectations exact


class TextTests(unittest.TestCase):
    def test_synonyms_fold_to_one_concept(self):
        self.assertEqual(ts.norm("analyse"), ts.norm("Analyzer"))
        self.assertEqual(ts.norm("closest"), ts.norm("similarity"))
        self.assertEqual(ts.norm("GitHub"), ts.norm("repository"))

    def test_github_is_not_split(self):  # regression: camelCase split produced "git hub"
        self.assertEqual(ts.terms("GitHub"), [ts.norm("github")])

    def test_stop_words_removed(self):
        self.assertEqual(ts.terms("I want to build a new app that already exists"), [])

    def test_requirement_concept_only_for_requirements_analysis(self):
        self.assertIn("requirements", ts.display(ts.concepts("requirement analysis tool")))
        self.assertNotIn("requirements", ts.display(ts.concepts("invoice app requirement: stripe billing")))

    def test_concepts_dedup_and_keywords(self):
        c = ts.display(ts.concepts("invoice invoices invoicing", ["stripe"]))
        self.assertEqual(c, ["invoice", "stripe"])

    def test_open_source_is_not_a_concept(self):
        self.assertEqual(ts.concepts("open source open-source"), [])


class SurfaceTests(unittest.TestCase):
    def test_labels_and_queries_use_real_words(self):  # regression: stems like "recurr" leaked into GitHub queries
        req = "recurring billing for hosted invoices"
        sm = ts.surface_map(req)
        self.assertEqual(ts.display(ts.concepts(req), sm), ["recurring", "invoice", "hosted"])
        self.assertEqual(ts.score(ts.concepts(req), [], IDF, sm)["missing"], ["recurring", "invoice", "hosted"])


class ScoreTests(unittest.TestCase):
    def test_full_match_is_100(self):
        rc = ts.concepts("stripe invoice")
        self.assertEqual(ts.score(rc, rc, IDF)["closeness"], 100)

    def test_no_overlap_is_0(self):
        s = ts.score(ts.concepts("stripe invoice"), ts.terms("weather forecast"), IDF)
        self.assertEqual((s["closeness"], s["matched"]), (0, []))
        self.assertEqual(s["missing"], ["stripe", "invoice"])

    def test_partial_and_bounds(self):
        s = ts.score(ts.concepts("stripe invoice kanban notes"), ts.terms("stripe invoice"), IDF)
        self.assertEqual(s["coverage"], 50)
        self.assertTrue(0 < s["closeness"] < 100)

    def test_empty_inputs(self):
        self.assertEqual(ts.score([], ["x"], IDF)["closeness"], 0)
        self.assertEqual(ts.score(["x"], [], IDF)["closeness"], 0)

    def test_rare_concepts_weigh_more(self):
        idf = lambda t: 5.0 if t == "stripe" else 1.0  # noqa: E731
        rc = ts.concepts("stripe invoice")
        self.assertGreater(ts.score(rc, ts.terms("stripe"), idf)["closeness"],
                           ts.score(rc, ts.terms("invoice"), idf)["closeness"])

    def test_clip(self):
        self.assertEqual(len(ts.clip("x" * 1000)), ts.MAX_DESC_CHARS)
        self.assertEqual(ts.clip(None), "")

    def test_verdict_bands(self):
        self.assertTrue(ts.verdict(70).startswith("Reuse"))
        self.assertTrue(ts.verdict(69).startswith("Fork"))
        self.assertTrue(ts.verdict(30).startswith("Borrow"))
        self.assertTrue(ts.verdict(29).startswith("Build new"))


if __name__ == "__main__":
    unittest.main()
