"""Application layer: orchestrates sources + scoring into one analysis result."""
from __future__ import annotations

import math
import threading
import time
from collections import Counter

from . import sources, textscore

MAX_REQUIREMENT_CHARS = 5000
MAX_KEYWORDS = 20
MAX_GITHUB_QUERIES = 5  # unauthenticated search allows 10/min; keeps 2 analyses/min possible

_lock = threading.Lock()
_catalog: dict | None = None


def catalog(reload: bool = False) -> dict:
    """Claude plugin catalog plus document frequencies (the IDF background corpus)."""
    global _catalog
    with _lock:
        if _catalog is None or reload:
            plugins, errors = sources.load_claude_plugins()
            df: Counter = Counter()
            for p in plugins:
                p["_terms"] = textscore.terms(f"{p['name'].replace('-', ' ')} {textscore.clip(p['description'])} {p.get('category', '')}")
                df.update(set(p["_terms"]))
            _catalog = {"plugins": plugins, "df": df, "errors": errors, "loaded_at": time.time()}
        return _catalog


def make_idf(cat: dict):
    n = len(cat["plugins"])
    df = cat["df"]
    return lambda t: math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0


class InputError(ValueError):
    pass


def validate(requirement, keywords) -> tuple[str, list[str]]:
    if not isinstance(requirement, str) or not requirement.strip():
        raise InputError("requirement must be a non-empty string")
    if len(requirement) > MAX_REQUIREMENT_CHARS:
        raise InputError(f"requirement exceeds {MAX_REQUIREMENT_CHARS} characters")
    keywords = keywords or []
    if not isinstance(keywords, list) or not all(isinstance(k, str) and len(k) <= 100 for k in keywords):
        raise InputError("keywords must be a list of strings (each <= 100 chars)")
    if len(keywords) > MAX_KEYWORDS:
        raise InputError(f"at most {MAX_KEYWORDS} keywords")
    return requirement.strip(), keywords


def github_queries(req_concepts: list[str], idf, surface: dict[str, str] | None = None) -> list[str]:
    """Rarest (most specific) concepts first; GitHub ANDs terms, so keep queries to 2-3 real words."""
    ws = textscore.display(sorted(req_concepts, key=lambda t: -idf(t)), surface)
    qs: list[str] = []
    if len(ws) >= 3:
        qs += [" ".join(ws[:3]), " ".join(ws[:2]), f"{ws[0]} {ws[2]}", f"{ws[1]} {ws[2]}"]
    elif ws:
        qs.append(" ".join(ws))
    if ws and "claude" not in ws[:3]:
        qs.append(f"{ws[0]} claude")
    seen: list[str] = []
    for q in qs:
        if q not in seen:
            seen.append(q)
    return seen[:MAX_GITHUB_QUERIES]


def analyze(requirement: str, keywords: list[str] | None = None, top: int = 10, github: bool = True) -> dict:
    requirement, keywords = validate(requirement, keywords)
    top = max(1, min(int(top), 50))
    t0 = time.time()
    cat = catalog()
    idf = make_idf(cat)
    rc = textscore.concepts(requirement, keywords)
    surface = textscore.surface_map(requirement, *keywords)

    plugin_results = []
    for p in cat["plugins"]:
        s = textscore.score(rc, p["_terms"], idf, surface)
        if s["closeness"] > 0:
            plugin_results.append({k: v for k, v in p.items() if not k.startswith("_")} | s)
    plugin_results.sort(key=lambda r: (-r["closeness"], r["name"].lower()))

    gh_results, errors, queries = [], list(cat["errors"]), []
    github_status = "skipped"
    if github and rc:
        repos: dict[str, dict] = {}
        github_status = "ok"
        for q in github_queries(rc, idf, surface):
            queries.append(q)
            try:
                for it in sources.search_repositories(f"{q} in:name,description,topics fork:false"):
                    repos.setdefault(it["full_name"], it)
            except sources.GitHubError as e:
                errors.append(str(e))
                github_status = "rate-limited" if e.rate_limited else "partial"
                if e.rate_limited:
                    break
        if not repos and github_status == "partial":
            github_status = "failed"
        for it in repos.values():
            rec = sources.repo_record(it)
            text = " ".join([rec["name"].split("/")[-1].replace("-", " ").replace("_", " "),
                             textscore.clip(rec["description"]), " ".join(rec["topics"]).replace("-", " ")])
            gh_results.append(rec | textscore.score(rc, textscore.terms(text), idf, surface))
        gh_results.sort(key=lambda r: (-r["closeness"], -r["stars"]))

    tops = [r for r in (plugin_results[:1] + gh_results[:1])]
    best = max(tops, key=lambda r: r["closeness"]) if tops else None
    best_pct = best["closeness"] if best else 0
    return {
        "requirement": requirement,
        "concepts": textscore.display(rc, surface),
        "claude_plugins": plugin_results[:top],
        "github": gh_results[:top],
        "github_status": github_status,
        "github_queries": queries,
        "github_authenticated": bool(sources.github_token()) if github else None,
        "catalog_size": len(cat["plugins"]),
        "best": {"name": best["name"], "url": best["url"], "closeness": best_pct} if best else None,
        "verdict": textscore.verdict(best_pct),
        "errors": errors,
        "method": "closeness = 75% IDF-weighted concept coverage + 25% TF-IDF cosine over name, description "
                  "and topics (lexical with synonyms, not semantic; review the top matches before reusing)",
        "elapsed_s": round(time.time() - t0, 2),
    }
