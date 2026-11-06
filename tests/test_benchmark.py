"""Retrieval-quality regression guard: the 2.0 ranker must not fall below the 1.x baseline on the labelled set."""
import contextlib
import io
import sys
import unittest
from pathlib import Path

import helpers  # noqa: F401

sys.path.insert(0, str(Path(__file__).parent / "benchmark"))
import run_benchmark  # noqa: E402


class BenchmarkTests(unittest.TestCase):
    def test_v2_not_worse_than_v1(self):
        with contextlib.redirect_stdout(io.StringIO()):
            r = run_benchmark.main()
        v1, v2 = r["v1 (1.x)"], r["v2 (2.0)"]
        for m in ("P@5", "R@10", "MRR", "NDCG@10"):
            self.assertGreaterEqual(v2[m], v1[m], m)

    def test_metrics_math(self):
        m = run_benchmark.metrics(["a", "b", "c"], {"b": 2, "c": 1})
        self.assertEqual((m["P@5"], m["R@10"], m["MRR"]), (0.4, 1.0, 0.5))
        self.assertLess(m["NDCG@10"], 1.0)
        self.assertEqual(run_benchmark.metrics(["b", "c"], {"b": 2, "c": 1})["NDCG@10"], 1.0)


if __name__ == "__main__":
    unittest.main()
