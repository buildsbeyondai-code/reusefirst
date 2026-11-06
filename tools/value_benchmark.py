#!/usr/bin/env python3
"""Phase 10 product-value harness: building WITHOUT ReuseFirst's reuse (arm A) vs WITH it (arm B).

Same model, prompt template, sandbox, limits and verification gates in both arms; only the reuse selection differs
(arm A: none; arm B: the candidates ReuseFirst's policy pre-selects). Every run spends real Claude usage, so it only
runs with --i-accept-cost and a per-run cap. Without it, it prints the plan and the worst-case spend (dry run).

  python3 tools/value_benchmark.py                       # dry run: plan + maximum spend
  python3 tools/value_benchmark.py --i-accept-cost --trials 3 --budget 3 --minutes 30

Outputs tools/value_results.jsonl (one line per run) and prints medians and IQR per arm: wall time, model-reported
cost, verification status, tests passed, gates failed, files. Small samples are reported as such, never as a saving.
"""
import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "req-analyzer" / "app"))

TASKS = [
    {"id": "invoice", "requirement": "Self-hosted invoicing web app: create clients and invoices, PDF export, mark paid/unpaid",
     "must_have": "Create client\nCreate invoice with line items\nExport invoice as PDF\nMark invoice paid"},
    {"id": "notes", "requirement": "Markdown notes web app with full-text search and tags",
     "must_have": "Create and edit notes in Markdown\nSearch notes by text\nTag notes and filter by tag"},
    {"id": "water", "requirement": "Daily water intake tracker web app with a goal and history chart",
     "must_have": "Log a drink\nSet a daily goal\nShow today's progress and a 7-day history"},
]


def answers(task, out, reuse, port, budget, minutes):
    return {"app_name": task["id"], "output_dir": str(out), "users": "Me, a single user", "platforms": "Browser on WSL2",
            "journeys": task["must_have"], "must_have": task["must_have"],
            "acceptance": "\n".join(f"Given the app, when I {m.lower()}, then it works and persists" for m in task["must_have"].splitlines()),
            "app_type": "Web app (browser UI + local server)", "reuse": reuse, "git": True, "port": port,
            "budget_usd": budget, "max_minutes": minutes, "model": "default"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-accept-cost", action="store_true")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--budget", type=float, default=3.0)
    ap.add_argument("--minutes", type=int, default=30)
    a = ap.parse_args()
    runs = len(TASKS) * 2 * a.trials
    print(f"Plan: {len(TASKS)} tasks x 2 arms x {a.trials} trials = {runs} builds; worst-case spend ${runs * a.budget:.2f} "
          f"(model-reported), up to {runs * a.minutes} minutes.")
    if not a.i_accept_cost:
        print("Dry run only. Live measurements: PENDING (pass --i-accept-cost to run).")
        return 0
    from reqanalyzer import builder, engine, gates, lifecycle
    out_file = ROOT / "tools" / "value_results.jsonl"
    mgr = builder.BuildManager(Path(tempfile.mkdtemp(prefix="value-state-")))
    for t in range(a.trials):
        for task in TASKS:
            analysis = engine.analyze(task["requirement"], top=5)
            _, picked, _ = builder.reuse_candidates(analysis)
            for arm, reuse in (("A-no-reuse", []), ("B-reusefirst", picked)):
                out = builder.APPS_DIR / f"vb-{task['id']}-{arm}-{t}-{int(time.time())}"
                job = mgr.start(task["requirement"], answers(task, out, reuse, gates_port(), a.budget, a.minutes))
                while lifecycle.is_active(mgr.get(job["id"])["status"]):
                    time.sleep(10)
                j = mgr.get(job["id"])
                rec = {"task": task["id"], "arm": arm, "trial": t, "status": j["status"], "reuse": len(reuse),
                       "minutes": round((j["finished_at"] - j["created_at"]) / 60, 2), "cost_usd": j.get("cost_usd"),
                       "tests_passed": (j.get("tests") or {}).get("passed"), "files": j.get("file_count"),
                       "gates_failed": sum(1 for g in j.get("gates") or [] if g["status"] == gates.FAILED)}
                with open(out_file, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                print(rec)
    summarise(out_file)
    return 0


def gates_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def summarise(path):
    rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    for arm in sorted({r["arm"] for r in rows}):
        rs = [r for r in rows if r["arm"] == arm]
        mins = [r["minutes"] for r in rs]
        cost = [r["cost_usd"] for r in rs if r["cost_usd"] is not None]
        print(arm, {"runs": len(rs), "succeeded": sum(r["status"] == "succeeded" for r in rs),
                    "median_minutes": statistics.median(mins), "median_cost_usd": statistics.median(cost) if cost else None,
                    "minutes_iqr": statistics.quantiles(mins, n=4) if len(mins) >= 4 else "n<4"})


if __name__ == "__main__":
    sys.exit(main())
