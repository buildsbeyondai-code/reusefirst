"""Application layer: orchestrates sources + scoring into one analysis result."""
from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as fwait

from . import policy, sources, textscore
from .obs import METRICS

MAX_REQUIREMENT_CHARS = 5000
MAX_KEYWORDS = 20
MAX_GITHUB_QUERIES = 5  # unauthenticated search allows 10/min; keeps 2 analyses/min possible
EVIDENCE_TOP = 5          # README inspection for the top N GitHub candidates (Stage D)
EVIDENCE_DEADLINE_S = 8
PROVIDER_DEADLINE_S = 25
METHOD = ("relevance = 75% IDF-weighted concept coverage + 25% TF-IDF cosine over name, description and topics, "
          "with generic action verbs (generate, track, manage...) down-weighted to 0.35. Lexical with synonyms, NOT semantic, and UNCALIBRATED: a relevance score, not a probability that "
          "reuse will succeed. Evidence confidence rises when a README confirms the concepts.")

LANGS = {"python": "Python", "django": "Python", "flask": "Python", "fastapi": "Python", "javascript": "JavaScript",
         "typescript": "TypeScript", "node": "JavaScript", "nodejs": "JavaScript", "react": "JavaScript",
         "rust": "Rust", "golang": "Go", "java": "Java", "kotlin": "Kotlin", "swift": "Swift", "c#": "C#",
         "dotnet": "C#", "php": "PHP", "ruby": "Ruby"}
LANG_FAMILY = {"TypeScript": {"JavaScript", "TypeScript"}, "JavaScript": {"JavaScript", "TypeScript"}}
PLATFORMS = {"windows": "Windows", "macos": "macOS", "mac": "macOS", "linux": "Linux", "android": "Android",
             "ios": "iOS", "iphone": "iOS", "wsl": "Linux", "browser": "Web", "web": "Web"}
INTEGRATIONS = ("stripe", "paypal", "slack", "github", "gitlab", "jira", "notion", "google", "gmail", "outlook",
                "twilio", "openai", "anthropic", "claude", "postgres", "postgresql", "mysql", "sqlite", "mongodb",
                "redis", "s3", "aws", "azure", "gcp", "linkedin", "whatsapp", "telegram", "discord", "shopify")

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


def make_idf(cat: dict, actions: bool = True):
    n = len(cat["plugins"])
    df = cat["df"]
    base = lambda t: math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0
    return textscore.weighted(base) if actions else base


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


def profile(requirement: str) -> dict:
    """Stage A: structured, deterministic decomposition of the requirement."""
    words = set(textscore.tokens(requirement))
    langs = sorted({LANGS[w] for w in words if w in LANGS})
    plats = sorted({PLATFORMS[w] for w in words if w in PLATFORMS})
    integ = sorted(w for w in words if w in INTEGRATIONS)
    lic = "permissive licence required" if re.search(r"\b(mit|apache|permissive|commercial)\b", requirement, re.I) else None
    offline = bool(re.search(r"\boffline|no internet|air.?gapped\b", requirement, re.I))
    return {"capabilities": [], "languages": langs, "platforms": plats, "integrations": integ,
            "licence_constraint": lic, "offline": offline}


def compatibility(rec: dict, prof: dict) -> tuple[str, list[str]]:
    lang = rec.get("language") or ""
    if prof["languages"] and lang:
        ok = any(lang in LANG_FAMILY.get(l, {l}) for l in prof["languages"])
        if not ok:
            return "fail", [f"written in {lang}; the requirement asks for {', '.join(prof['languages'])}"]
        return "pass", [f"language {lang} matches"]
    text = " ".join([rec.get("description", ""), " ".join(rec.get("topics") or [])]).lower()
    for p in prof["platforms"]:
        others = [o for o in ("windows", "macos", "linux", "android", "ios") if o != p.lower()]
        if p.lower() not in text and any(re.search(rf"\b{o}\b", text) for o in others) and p != "Web":
            if re.search(r"\b(only|exclusive)\b", text):
                return "fail", [f"described as for another platform than {p}"]
    return "unknown", ["language/platform not stated or not constrained"]


def evidence(rec: dict, readme: str | None, rc: list[str]) -> dict:
    """Heuristic, uncalibrated confidence in the match evidence (0-90; never 100 without human/semantic review)."""
    desc_words = len(textscore.tokens(rec.get("description", "")))
    conf = 25 + (15 if desc_words >= 8 else 5 if desc_words >= 3 else 0) + (10 if len(rec.get("topics") or []) >= 2 else 0)
    sources_ = ["name", "description"] + (["topics"] if rec.get("topics") else [])
    confirmed: list[str] = []
    if readme:
        rterms = set(textscore.terms(readme[: sources.README_MAX_BYTES]))
        confirmed = [t for t in rc if t in rterms]
        conf += 25 + round(15 * len(confirmed) / max(1, len(rc)))
        sources_.append("readme")
    return {"confidence": min(90, conf), "sources": sources_, "readme_inspected": bool(readme),
            "confirmed_in_readme": confirmed, "label": "heuristic, uncalibrated"}


def recommend(rec: dict) -> str:
    cov, conf = rec.get("coverage", 0), (rec.get("evidence") or {}).get("confidence", 0)
    lic = (rec.get("licence") or {}).get("reuse", "review")
    if cov >= 50 and conf < 35:
        return "insufficient evidence"
    if rec.get("compatibility") == "fail":
        return "borrow ideas" if cov >= 30 else "build new"
    if cov >= 70 and lic == "allowed" and (rec.get("maintenance") or {}).get("state") not in ("archived", "unmaintained"):
        return "reuse"
    if cov >= 50 and lic != "learn-only":
        return "extend"
    if cov >= 30:
        return "borrow ideas" if lic == "learn-only" else "borrow"
    return "build new"


def _enrich(rec: dict, prof: dict, readme: str | None, rc: list[str]) -> dict:
    rec["relevance"] = rec["closeness"]
    if "licence" not in rec:
        rec["licence"] = policy.licence_class(rec.get("license") if rec.get("license") not in (None, "see repo") else None) \
            if rec.get("license") else {"spdx": "unknown", "class": "unknown", "reuse": "review",
                                         "reason": "licence not listed in the plugin catalog: check the repository"}
    rec["compatibility"], rec["compatibility_reasons"] = compatibility(rec, prof)
    rec["evidence"] = evidence(rec, readme, rc)
    m = rec.get("maintenance") or {"state": "unknown", "risk": "unknown"}
    rec["maintenance"] = m
    rec["security_risk"] = m.get("risk", "unknown") if m.get("state") != "active" else "unknown"
    rec["recommendation"] = recommend(rec)
    rec["auto_reuse_eligible"], rec["not_eligible_because"] = policy.auto_reuse_eligible(rec)
    return rec


def _score_text(name: str, desc: str, topics) -> list[str]:
    nm = name.split("/")[-1].replace("-", " ").replace("_", " ")
    return textscore.terms(" ".join([nm, textscore.clip(desc), " ".join(topics or []).replace("-", " ")]))


def semantic_stage(requirement: str, result: dict, readmes: dict) -> dict:
    """Optional Claude review of the top candidates (semantic.py); recommendations are recomputed with the fit."""
    from . import builder, semantic
    cands = sorted(result["github"] + result["claude_plugins"] + result["packages"],
                   key=lambda c: (-c["closeness"], c.get("id", "")))
    try:
        st = semantic.review(requirement, cands, readmes, builder.run_claude_json)
    except builder.BuildError as e:
        METRICS.inc("semantic_failures")
        return {"status": "failed", "reviewed": 0, "error": str(e)[:300]}
    for c in cands:
        if c.get("semantic"):
            c["recommendation"] = recommend({**c, "coverage": c["semantic"]["fit"]})
            c["auto_reuse_eligible"], c["not_eligible_because"] = policy.auto_reuse_eligible(
                {**c, "coverage": min(c["coverage"], c["semantic"]["fit"])})  # both signals must agree
    result["confidence_mode"] = "lexical + Claude semantic review of the top candidates"
    return st


def analyze(requirement: str, keywords: list[str] | None = None, top: int = 10, github: bool = True,
            packages: bool = True, inspect: bool = True, semantic: bool = False) -> dict:
    requirement, keywords = validate(requirement, keywords)
    top = max(1, min(int(top), 50))
    t0 = time.time()
    METRICS.inc("analyses")
    cat = catalog()
    idf = make_idf(cat)
    rc = textscore.concepts(requirement, keywords)
    surface = textscore.surface_map(requirement, *keywords)
    prof = profile(requirement)
    prof["capabilities"] = textscore.display(rc, surface)
    providers = [{"id": "claude-plugins", "status": "ok" if not cat["errors"] else "partial", "items": len(cat["plugins"])}]

    plugin_results = []
    for p in cat["plugins"]:
        s = textscore.score(rc, p["_terms"], idf, surface)
        if s["closeness"] > 0:
            plugin_results.append({k: v for k, v in p.items() if not k.startswith("_")} | s)
    plugin_results.sort(key=lambda r: (-r["closeness"], r["name"].lower(), r.get("id", "")))
    plugin_results = [_enrich(r, prof, None, rc) for r in plugin_results[:top]]

    gh_results, errors, queries = [], list(cat["errors"]), []
    readmes: dict[str, str | None] = {}
    github_status = "skipped"
    stale = False
    if github and rc:
        repos: dict[str, dict] = {}
        github_status = "ok"
        for q in github_queries(rc, idf, surface):
            queries.append(q)
            try:
                for it in sources.search_repositories(f"{q} in:name,description,topics fork:false"):
                    repos.setdefault(it["full_name"].lower(), it)
            except sources.GitHubError as e:
                errors.append(str(e))
                METRICS.inc("provider_failures")
                github_status = "rate-limited" if e.rate_limited else "partial"
                if e.rate_limited:
                    break
        if not repos and github_status == "partial":
            github_status = "failed"
        for it in repos.values():
            rec = sources.repo_record(it)
            gh_results.append(rec | textscore.score(rc, _score_text(rec["name"], rec["description"], rec["topics"]), idf, surface))
        gh_results.sort(key=lambda r: (-r["closeness"], -r["stars"], r["id"]))
        gh_results = gh_results[:top]
        if inspect and github_status != "rate-limited":
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(sources.fetch_readme, r["name"]): r["name"] for r in gh_results[:EVIDENCE_TOP]}
                done, _ = fwait(futs, timeout=EVIDENCE_DEADLINE_S)
                for f in done:
                    readmes[futs[f]] = f.result()
        gh_results = [_enrich(r, prof, readmes.get(r["name"]), rc) for r in gh_results]
        providers.append({"id": "github", "status": github_status, "items": len(repos), "queries": len(queries),
                          "readmes_inspected": sum(1 for v in readmes.values() if v)})
        stale = any((sources.cached_at(q + " in:name,description,topics fork:false") or time.time()) < time.time() - 600
                    for q in queries)

    pkg_results: list[dict] = []
    if github and packages and rc:
        q = " ".join(textscore.display(sorted(rc, key=lambda t: -idf(t)), surface)[:3])
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {ex.submit(sources.search_npm, q): "npm", ex.submit(sources.search_crates, q): "crates.io"}
            done, pending = fwait(futs, timeout=PROVIDER_DEADLINE_S)
            for f in futs:
                pid = futs[f]
                if f not in done:
                    providers.append({"id": pid, "status": "timed-out", "items": 0})
                    continue
                try:
                    items = f.result()
                    providers.append({"id": pid, "status": "ok", "items": len(items)})
                except sources.GitHubError as e:
                    errors.append(str(e))
                    providers.append({"id": pid, "status": "failed", "items": 0})
                    continue
                for it in items:
                    pkg_results.append(it | textscore.score(rc, _score_text(it["name"], it["description"], it["topics"]), idf, surface))
        pkg_results = [r for r in pkg_results if r["closeness"] > 0]
        pkg_results.sort(key=lambda r: (-r["closeness"], r["id"]))
        pkg_results = [_enrich(r, prof, None, rc) for r in pkg_results[:top]]

    tops = plugin_results[:1] + gh_results[:1]
    best = max(tops, key=lambda r: (r["closeness"], r.get("coverage", 0))) if tops else None
    best_pct = best["closeness"] if best else 0
    result = {
        "requirement": requirement,
        "concepts": textscore.display(rc, surface),
        "profile": prof,
        "claude_plugins": plugin_results,
        "github": gh_results,
        "packages": pkg_results,
        "providers": providers,
        "github_status": github_status,
        "github_queries": queries,
        "github_authenticated": bool(sources.github_token()) if github else None,
        "stale": stale,
        "catalog_size": len(cat["plugins"]),
        "best": {"name": best["name"], "url": best["url"], "closeness": best_pct,
                 "recommendation": best["recommendation"]} if best else None,
        "errors": errors,
        "method": METHOD,
        "confidence_mode": "lexical-only (reduced confidence: no semantic model)",
    }
    if semantic:
        result["semantic"] = semantic_stage(requirement, result, readmes if github and rc else {})
    from . import decision
    result["decision"] = decision.decide(result)
    result["verdict"] = decision.VERDICT_TEXT[result["decision"]["recommendation"]]
    result["elapsed_s"] = round(time.time() - t0, 2)
    METRICS.set("last_analysis_s", result["elapsed_s"])
    return result
