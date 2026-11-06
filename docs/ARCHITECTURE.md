# Architecture

Layered modular monolith, one process, stdlib only. Dependencies point downward.

```
static/ (UI: index.html, app.js, app.css)     cli.py (Claude plugin entry)
            \                                   /
             server.py  (HTTP, 127.0.0.1:5057, validation, security headers)
                          |
                      engine.py  (orchestration: catalog + queries + ranking + verdict)
                     /          \
       textscore.py (pure scoring)   sources.py (adapters: plugin catalogs on disk, GitHub REST)
```

Data flow: requirement → `textscore.concepts` (stop words, stems, synonyms) → plugin catalog scored locally →
≤5 GitHub `search/repositories` queries (rarest concepts first, `in:name,description,topics fork:false`) → each repo scored →
top N per source + verdict.

Data sources (provenance):
- `~/.claude/plugins/plugin-directory-cache-v2.json` — Claude Code's own plugin directory cache (refreshed by Claude Code).
- `~/.claude/plugins/marketplaces/*/.claude-plugin/marketplace.json` — installed marketplaces.
- `https://api.github.com/search/repositories` — live; cached in memory 15 min.

Trust boundaries: browser → server (localhost only, JSON only); server → GitHub (HTTPS, optional token in Authorization header only);
repo/plugin text is untrusted data rendered with `textContent` (no innerHTML) and only `https:` links.

Failure modes: catalog missing/corrupt → listed in `errors`, plugin list empty; GitHub 403/429 → `rate-limited`, stop querying;
GitHub down → `failed`; port in use → server exits 76 (hook then leaves the existing server alone).

Build tab (`builder.py`, application layer):
- `required_inputs()` = standard UAISES-grouped fields + `claude -p --tools "" --json-schema` (UAISES §2 text in the prompt) → sanitised
  (select values checked, secrets/duplicates dropped, max 12 questions). Reuse checklist comes from `engine.analyze` (closest pre-ticked).
- `BuildManager` = single worker thread per build, one build at a time. Writes BUILD_SPEC.md + the UAISES standard into the new folder, runs
  `claude -p --output-format stream-json --permission-mode dontAsk --allowedTools <allowlist> --max-budget-usd N` with cwd = new folder,
  own process group (cancel/timeout kill the group), streams events → `summarize()` → job.events; job.json saved atomically every 5 s
  under `~/.local/state/req-analyzer/builds/<id>/` with the raw `stream.jsonl`.
- Trust boundary: the build executes code as the user. Mitigations: localhost + Host check + JSON-only + session token, folder confinement
  (Claude Code edits limited to cwd), allowlist without rm/sudo/push/arbitrary curl, spending cap, time limit.

Plugin: `.claude-plugin/plugin.json`, `commands/req-analyze.md`, `skills/requirement-analysis/SKILL.md`,
`hooks/hooks.json` → `hooks/ensure_server.py` (SessionStart; starts the server detached if 5057 is free).
