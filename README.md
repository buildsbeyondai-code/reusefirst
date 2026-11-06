# ReuseFirst — Reuse-First Builder (Claude Code plugin + local web UI) · 2.0

Before building an app from a requirement, ReuseFirst finds what already exists. It searches **Claude Code
plugins** (your installed marketplaces and the plugin directory cache, ~3,800), **GitHub repositories**, and the
**npm** and **crates.io** registries. It then answers the real question: **is reusing actually better than
building?**

Each candidate gets:
- an uncalibrated relevance score;
- concept coverage, plus the concepts it does not cover;
- evidence confidence (higher when ReuseFirst read its README);
- licence class and reuse right;
- language compatibility and maintenance state;
- a recommendation: reuse, extend, borrow, build new, or *insufficient evidence*.

A decision panel compares reuse and build-new effort ranges, with assumptions and sensitivity.

- Web UI: http://127.0.0.1:5057/ (SysPerf keeps 5056)
- In Claude Code: `/reusefirst:reusefirst <requirement>` (or `status`), or just ask "does something like this already exist?"
- CLI: `PYTHONPATH=plugins/req-analyzer/app python3 -m reqanalyzer.cli --markdown "your requirement"`

## Build tab: sandboxed and independently verified
1. **List required inputs.** Every input needed to build the app, grouped by UAISES section and pre-filled by Claude.
   Reuse candidates are **pre-ticked only when they pass the reuse policy**: coverage ≥ 50%, permissive licence,
   maintained, enough evidence, not a fork (docs/REUSE_POLICY.md).
2. **Create app** (or **Enhance** an app in `~/apps`). The build runs in this order:
   1. ReuseFirst clones the ticked projects itself, at a pinned commit, licence-checked, and writes
      `docs/REUSE_PROVENANCE.md`.
   2. Claude Code builds headless **inside a bubblewrap sandbox**. Your home is hidden, only the app folder is
      writable, and the network reaches only the Claude API and package registries (docs/SECURITY_MODEL.md).
   3. ReuseFirst **re-runs the tests and checks itself**: syntax, secrets, OSV vulnerabilities, SBOM, provenance,
      a sandboxed start-up check, and regression for enhancements. The result goes in
      `docs/VERIFICATION_REPORT.md`.

   The build is `succeeded` only if every mandatory check passes; otherwise it is `partially_completed` or `failed`,
   with reasons (docs/BUILD_LIFECYCLE.md). Enhancements work on a staging copy and replace the app atomically only
   when everything passes.
3. **Launch app** runs a verified app in the sandbox, forwards only its port, health-checks it, and offers **Stop**.

Every build follows the bundled UAISES (engineering) and UEUIS (UI: ISO 9241, WCAG 2.2 AA) standards.

## Install
```
/plugin marketplace add buildsbeyondai-code/reusefirst
/plugin install reusefirst@reusefirst
```
**Requirements:**
- Linux or WSL2 with Python 3.11+ (standard library only).
- Builds also need the Claude Code CLI and **bubblewrap** (`sudo apt install bubblewrap`). On Ubuntu 24.04 outside
  WSL, unprivileged user namespaces may need enabling. Without a verified sandbox, builds are **blocked** and
  analysis still works; the status bar says why.
- The SessionStart hook starts the web UI if port 5057 is free.

**Upgrading from 1.x:** see docs/MIGRATION_2.0.md. The API now needs the session token on every route.

## Honest limits
- Relevance is **lexical** (IDF-weighted coverage + TF-IDF cosine, generic verbs down-weighted) and **not
  calibrated**: it is not a probability that reuse will succeed. Tick **Deep check with Claude** for a semantic
  review of the top 8 candidates. That improved the labelled benchmark from NDCG@10 0.763 to 0.908, but the labels
  are Claude-made, so the comparison is circular.
- On a 12-query labelled benchmark, 2.0's ranking beats 1.x (NDCG@10 0.763 vs 0.740). The labels were made by the
  assistant, not independent humans (docs/BENCHMARKS.md).
- A real end-to-end build with real Claude inside the 2.0 sandbox has **not yet been verified**: it spends usage.
  The pipeline is tested with a fake Claude CLI and real sandboxing.
- Whether building with ReuseFirst saves time or money is **not measured yet**. The A/B harness is ready
  (`tools/value_benchmark.py`, live runs pending).

## Development
- Tests: `python3 -m unittest discover -s tests` (188 tests, ~30 s; needs bwrap for the sandbox tests).
- Lint: `ruff check .`. Coverage: `coverage run -m unittest discover -s tests && coverage report` (dev tools are in
  `tools/requirements-dev.lock`).
- Browser E2E: `tests/e2e_browser.py <url>` (Playwright). Mutation check: `python3 tools/mutate.py`.
- Benchmark: `python3 tests/benchmark/run_benchmark.py`.
- CI: `.github/workflows/ci.yml`.

Docs: ARCHITECTURE, SECURITY_MODEL, DISCOVERY_ENGINE, REUSE_POLICY, BUILD_LIFECYCLE, QUALITY_GATES, BENCHMARKS,
SECURITY_TEST_REPORT, AUDIT_BASELINE, FINAL_AUDIT (all in `docs/`). License: MIT.
