"""Domain layer: is reusing actually better than building? (Phase 4)

Effort is in *relative effort units* (1 unit ≈ building and testing one requirement capability from scratch),
not hours, to avoid false precision. Every estimate is a range with stated assumptions, a confidence, and a
sensitivity check. Measured build outcomes (numbers only) are summarised alongside, never fed back as instructions.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

VERDICT_TEXT = {
    "reuse": "Reuse: install/configure the top match",
    "extend": "Fork or extend the top match",
    "borrow": "Borrow parts; build the rest",
    "build new": "Build new: no close match found",
    "insufficient evidence": "Build new or review by hand: insufficient evidence to reuse",
}
INTEGRATION = {"pass": 1.0, "unknown": 2.0, "fail": 4.0}
LICENCE = {"allowed": 0.0, "review": 1.5, "learn-only": None}  # None = code cannot be copied
MAINT = {"active": 0.0, "unknown": 1.0, "stale": 1.0, "unmaintained": 2.5, "archived": 3.0}


def reuse_cost(c: dict, n_caps: int) -> dict | None:
    lic = LICENCE.get((c.get("licence") or {}).get("reuse", "review"), 1.5)
    if lic is None:
        return None
    missing = len(c.get("missing") or [])
    integ = INTEGRATION.get(c.get("compatibility", "unknown"), 2.0)
    maint = MAINT.get((c.get("maintenance") or {}).get("state", "unknown"), 1.0)
    conf = (c.get("evidence") or {}).get("confidence", 25)
    uncertainty = (100 - conf) / 25  # weaker evidence = wider range
    low = missing * 1.0 + integ + lic + maint
    high = missing * 2.0 + integ * 2 + lic * 2 + maint * 2 + uncertainty + 0.25 * n_caps
    return {"low": round(low, 1), "high": round(high, 1), "mid": round((low + high) / 2, 1),
            "parts": {"missing_capabilities": missing, "integration": integ, "licence_overhead": lic,
                      "maintenance_exposure": maint, "evidence_uncertainty": round(uncertainty, 1)}}


def decide(result: dict) -> dict:
    caps = max(1, len(result.get("concepts") or []))
    build = {"low": round(1.0 * caps + 2, 1), "high": round(2.0 * caps + 4, 1)}
    build["mid"] = round((build["low"] + build["high"]) / 2, 1)
    cands = [c for c in (result.get("github") or []) + (result.get("claude_plugins") or []) + (result.get("packages") or [])
             if c.get("coverage", 0) >= 30]
    cands.sort(key=lambda c: (-c.get("coverage", 0), -c.get("closeness", 0), c.get("id", "")))
    options = []
    for c in cands[:3]:
        cost = reuse_cost(c, caps)
        strategy = "reuse" if c.get("coverage", 0) >= 70 else "extend" if c.get("coverage", 0) >= 50 else "borrow"
        options.append({"candidate": c.get("name"), "id": c.get("id"), "url": c.get("url"), "strategy": strategy,
                        "coverage": c.get("coverage", 0), "confidence": (c.get("evidence") or {}).get("confidence", 0),
                        "effort": cost, "copyable": cost is not None,
                        "candidate_recommendation": c.get("recommendation")})
    viable = [o for o in options if o["copyable"]]
    best = min(viable, key=lambda o: o["effort"]["mid"]) if viable else None
    if not best:
        rec = "insufficient evidence" if options else "build new"
    elif best["candidate_recommendation"] == "insufficient evidence":
        rec = "insufficient evidence"
    elif best["effort"]["high"] < build["low"]:
        rec = best["strategy"]
    elif best["effort"]["mid"] < build["mid"]:
        rec = best["strategy"] if best["strategy"] != "reuse" else "extend"
    else:
        rec = "build new"
    sens = []
    if best:
        doubled = best["effort"]["mid"] + best["effort"]["parts"]["missing_capabilities"] * 1.5
        sens.append(f"If each missing capability costs twice as much, reusing {best['candidate']} costs about "
                    f"{doubled:.1f} units against {build['mid']} to build new: "
                    f"{'building new would win' if doubled > build['mid'] else 'reuse still wins'}.")
        overlap = not (best["effort"]["high"] < build["low"] or build["high"] < best["effort"]["low"])
        if overlap:
            sens.append("The reuse and build ranges overlap: the choice is sensitive to the assumptions below.")
    return {
        "recommendation": rec, "build_new": build, "options": options,
        "confidence": "low" if not best or best["confidence"] < 50 else "medium" if best["confidence"] < 70 else "medium-high",
        "assumptions": [
            "1 unit = building and testing one requirement capability from scratch",
            "integration cost: 1 when the language matches, 2 when unknown, 4 when incompatible",
            "licence overhead: 0 permissive, 1.5 needs review; no-licence code cannot be copied",
            "maintenance exposure: 0 active, 1 stale/unknown, 2.5 unmaintained, 3 archived",
            "coverage is lexical (names, descriptions, topics, READMEs), not verified functionality",
        ],
        "sensitivity": sens,
        "units": "relative effort units",
    }


def report_markdown(rec: dict) -> str:
    """Exportable decision report for a saved analysis."""
    r = rec.get("result") or {}
    d = r.get("decision") or decide(r)
    rows = "\n".join(f"| {o['candidate']} | {o['strategy']} | {o['coverage']}% | {o['confidence']}% | "
                     + (f"{o['effort']['low']}–{o['effort']['high']}" if o["effort"] else "cannot copy (licence)") + " |"
                     for o in d["options"]) or "| (no candidate with ≥30% coverage) | | | | |"
    return f"""# ReuseFirst decision report

- Requirement: {r.get('requirement', '').strip()[:2000]}
- Analysed: {time.strftime('%Y-%m-%d %H:%M', time.localtime(rec.get('created_at', time.time())))}
- **Recommendation: {d['recommendation']}** (confidence: {d['confidence']})
- Build new: {d['build_new']['low']}–{d['build_new']['high']} {d['units']}

| Candidate | Strategy | Concept coverage | Evidence confidence | Reuse effort |
|---|---|---|---|---|
{rows}

## Sensitivity
{chr(10).join('- ' + x for x in d['sensitivity']) or '- n/a'}

## Assumptions
{chr(10).join('- ' + x for x in d['assumptions'])}

Scores are uncalibrated lexical relevance, not probabilities of success. Method: {r.get('method', '')}
"""


def outcome_summary(path: Path) -> dict:
    """Measured build outcomes: median minutes and cost, with and without reuse."""
    rows = []
    try:
        for ln in Path(path).read_text().splitlines()[-2000:]:
            try:
                rows.append(json.loads(ln))
            except ValueError:
                continue
    except OSError:
        pass

    def summ(rs):
        mins = [r["minutes"] for r in rs if isinstance(r.get("minutes"), (int, float))]
        cost = [r["cost_usd"] for r in rs if isinstance(r.get("cost_usd"), (int, float))]
        ok = sum(1 for r in rs if r.get("status") == "succeeded")
        return {"builds": len(rs), "succeeded": ok,
                "median_minutes": round(statistics.median(mins), 1) if mins else None,
                "median_cost_usd": round(statistics.median(cost), 2) if cost else None,
                "minutes_iqr": [round(q, 1) for q in statistics.quantiles(mins, n=4)[::2]] if len(mins) >= 4 else None}
    return {"with_reuse": summ([r for r in rows if r.get("reuse_count")]),
            "without_reuse": summ([r for r in rows if not r.get("reuse_count")]),
            "note": "measured on this PC; small samples are not evidence of a general saving"}
