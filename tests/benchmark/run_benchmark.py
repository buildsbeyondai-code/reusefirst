"""Retrieval benchmark: v1 (1.x lexical) vs v2 (2.0 ranking) on labelled requirements. Deterministic, offline.

  python3 tests/benchmark/run_benchmark.py            # from the committed snapshot (reproducible anywhere)
  python3 tests/benchmark/run_benchmark.py --snapshot # rebuild snapshot.json from this PC's plugin catalog

Metrics: Precision@5 (grade>=1), Recall@10 (of judged-relevant in the pool), MRR (first grade>=1), NDCG@10 (graded),
ranking latency per query. See docs/BENCHMARKS.md for limitations (assistant-made labels, pooled judgements).
"""
import json
import math
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "plugins" / "req-analyzer" / "app"))
from reqanalyzer import engine, textscore

QUERIES = json.loads((HERE / "queries.json").read_text())
QRELS = json.loads((HERE / "qrels.json").read_text())["qrels"]


def v1_terms(p):  # 1.x scoring text
    return textscore.terms(f"{p['name'].replace('-', ' ')} {textscore.clip(p['description'])} {p.get('category', '')}")


def v2_terms(p):
    return engine._score_text(p["name"], p["description"], [p.get("category", "")])


RANKERS = {"v1 (1.x)": v1_terms, "v2 (2.0)": v2_terms}
WEIGHTED = {"v1 (1.x)": False, "v2 (2.0)": True}  # v2 = action-verb weighting (textscore.ACTIONS)


def rank(rc, items, idf, terms_of):
    scored = [(textscore.score(rc, terms_of(p), idf)["closeness"], p) for p in items]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], x[1]["name"].lower(), x[1]["id"]))
    return [p["id"] for _, p in scored]


def metrics(ranked, qrel):
    rel = {k for k, g in qrel.items() if g >= 1}
    p5 = sum(1 for d in ranked[:5] if d in rel) / 5
    r10 = sum(1 for d in ranked[:10] if d in rel) / len(rel) if rel else 0.0
    mrr = next((1 / (i + 1) for i, d in enumerate(ranked) if d in rel), 0.0)
    dcg = sum((2 ** qrel.get(d, 0) - 1) / math.log2(i + 2) for i, d in enumerate(ranked[:10]))
    ideal = sorted(qrel.values(), reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return {"P@5": p5, "R@10": r10, "MRR": mrr, "NDCG@10": dcg / idcg if idcg else 0.0}


def build_snapshot():
    cat = engine.catalog()
    items, ids = [], set()
    for q in QUERIES:
        rc = textscore.concepts(q["requirement"])
        for name, terms_of in RANKERS.items():
            idf = engine.make_idf(cat, actions=WEIGHTED[name])
            scored = sorted(((textscore.score(rc, terms_of(p), idf)["closeness"], p) for p in cat["plugins"]),
                            key=lambda x: (-x[0], x[1]["name"].lower(), x[1].get("id", "")))
            for s, p in scored[:15]:
                if s > 0 and p["id"] not in ids:
                    ids.add(p["id"])
                    items.append({"id": p["id"], "name": p["name"], "description": textscore.clip(p["description"]),
                                  "category": p.get("category", "")})
    vocab = {t for it in items for t in v1_terms(it) + v2_terms(it)}
    vocab |= {t for q in QUERIES for t in textscore.concepts(q["requirement"])}
    snap = {"n": len(cat["plugins"]), "df": {t: cat["df"].get(t, 0) for t in sorted(vocab)}, "items": items,
            "built": time.strftime("%Y-%m-%d")}
    (HERE / "snapshot.json").write_text(json.dumps(snap, indent=0))
    print(f"snapshot: {len(items)} items, catalog N={snap['n']}")


def main():
    if "--snapshot" in sys.argv:
        return build_snapshot()
    snap = json.loads((HERE / "snapshot.json").read_text())
    n, df = snap["n"], snap["df"]
    base = lambda t: math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0
    report = {}
    for name, terms_of in RANKERS.items():
        idf = textscore.weighted(base) if WEIGHTED[name] else base
        per, lat = [], []
        for q in QUERIES:
            t0 = time.perf_counter()
            ranked = rank(textscore.concepts(q["requirement"]), snap["items"], idf, terms_of)
            lat.append((time.perf_counter() - t0) * 1000)
            per.append(metrics(ranked, QRELS[q["id"]]))
        report[name] = {m: round(statistics.mean(p[m] for p in per), 3) for m in per[0]} | {
            "median_ms_per_query (pool only)": round(statistics.median(lat), 2),
            "per_query_NDCG@10": [round(p["NDCG@10"], 2) for p in per]}
    print(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    main()
