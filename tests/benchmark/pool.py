"""Builds the labelling pool: union of the top-K plugins from the v1 and v2 rankers over the REAL local catalog."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "req-analyzer" / "app"))
from reqanalyzer import engine, textscore

QUERIES = json.loads((Path(__file__).parent / "queries.json").read_text())


def v1_terms(p):
    return textscore.terms(f"{p['name'].replace('-', ' ')} {textscore.clip(p['description'])} {p.get('category', '')}")


def v2_terms(p):
    return engine._score_text(p["name"], p["description"], [p.get("category", "")])


def rank(rc, plugins, idf, terms_of, k):
    scored = [(textscore.score(rc, terms_of(p), idf)["closeness"], p) for p in plugins]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], x[1]["name"].lower(), x[1].get("id", "")))
    return [p for _, p in scored[:k]]


if __name__ == "__main__":
    cat = engine.catalog()
    idf = engine.make_idf(cat)
    out = {}
    for q in QUERIES:
        rc = textscore.concepts(q["requirement"])
        pool = {p["id"]: p for p in rank(rc, cat["plugins"], idf, v1_terms, 15) + rank(rc, cat["plugins"], idf, v2_terms, 15)}
        out[q["id"]] = [{"id": p["id"], "name": p["name"], "description": p["description"][:300],
                         "category": p.get("category", "")} for p in pool.values()]
    print(json.dumps(out, indent=1))
