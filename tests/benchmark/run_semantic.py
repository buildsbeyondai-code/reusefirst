"""Semantic re-ranking evaluation: Claude's functional-fit judgement re-orders the v2 top 15 (ties keep v2 order).

  python3 tests/benchmark/run_semantic.py --i-accept-cost   # calls Claude (12 queries), caches judgements
  python3 tests/benchmark/run_semantic.py                   # offline: recomputes metrics from the cached judgements

CAVEAT: the relevance labels were also written by Claude, so this comparison is circular. It shows agreement with the
labeller more than true retrieval quality. Independent human labels are needed for a real claim.
"""
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "plugins" / "req-analyzer" / "app"))
import run_benchmark as b
from reqanalyzer import semantic, textscore

CACHE = HERE / "semantic_judgements.json"


def main():
    snap = json.loads((HERE / "snapshot.json").read_text())
    n, df = snap["n"], snap["df"]
    idf = textscore.weighted(lambda t: math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0)
    items = {i["id"]: i for i in snap["items"]}
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    live = "--i-accept-cost" in sys.argv
    cost = 0.0
    rows = {"v2 (2.0)": [], "v2 + semantic": []}
    for q in b.QUERIES:
        ranked = b.rank(textscore.concepts(q["requirement"]), snap["items"], idf, b.v2_terms)
        top = ranked[:15]
        if q["id"] not in cache:
            if not live:
                print(f"{q['id']}: no cached judgement; run with --i-accept-cost")
                return 1
            from reqanalyzer import builder
            cands = [dict(items[i], source="Claude plugin directory") for i in top]
            out = []
            for chunk in (cands[:8], cands[8:]):
                if not chunk:
                    continue
                res = builder.run_claude_json(semantic.prompt(q["requirement"], chunk, {}), semantic.SCHEMA)
                cost += res.get("_cost_usd") or 0
                out += res.get("items") or []
            cache[q["id"]] = {str(o["id"]): int(o["fit"]) for o in out if o.get("id") in top}
            CACHE.write_text(json.dumps(cache, indent=1))
        fit = cache[q["id"]]
        reranked = sorted(top, key=lambda i: (-fit.get(i, -1), top.index(i))) + ranked[15:]
        rows["v2 (2.0)"].append(b.metrics(ranked, b.QRELS[q["id"]]))
        rows["v2 + semantic"].append(b.metrics(reranked, b.QRELS[q["id"]]))
    report = {k: {m: round(statistics.mean(p[m] for p in v), 3) for m in v[0]} for k, v in rows.items()}
    report["v2 + semantic"]["per_query_NDCG@10"] = [round(p["NDCG@10"], 2) for p in rows["v2 + semantic"]]
    if live:
        report["model_reported_cost_usd"] = round(cost, 3)
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
