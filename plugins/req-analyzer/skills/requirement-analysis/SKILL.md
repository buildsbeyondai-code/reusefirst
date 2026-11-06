---
name: requirement-analysis
description: Use before building a new app, tool, feature or Claude plugin from a requirement, or when the user asks whether something "already exists", for "alternatives", "prior art", or "should I build or reuse". Searches installed Claude plugin catalogs and GitHub for the closest existing projects and scores closeness in %.
---

# Requirement reuse analysis

Before designing a new application from a requirement, check what already exists.

Run (keywords = 3-8 precise capability words you extract from the requirement):

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/app" python3 -m reqanalyzer.cli --markdown -k "kw1" -k "kw2" "requirement text"
```

- JSON output (drop `--markdown`) has `claude_plugins[]`, `github[]`, `verdict`, `best`, `errors`, `github_status`.
- Closeness = 75% IDF-weighted concept coverage + 25% TF-IDF cosine over name/description/topics. It is lexical: confirm the top matches really do the job before recommending reuse, and say so when they only share vocabulary.
- Verdict bands: >=70 reuse, 50-69 fork/extend, 30-49 borrow parts, <30 build new.
- If `github_status` is `rate-limited` or `failed`, report it; do not fill gaps from memory as if they were results.
- Prefer candidates with a permissive license, recent updates and real adoption (stars), and state the gaps the user would still need to build.
- Web UI for the user: http://127.0.0.1:5057/ (tab 1 Analyze; tab 2 Build app lists all UAISES inputs and builds the app non-interactively, reusing the closest matches, to UAISES and the UEUIS UI standard: ISO 9241 / WCAG 2.2 AA).
