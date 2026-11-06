# Architecture

Layered modular monolith, one process, stdlib only (2.0). Dependencies point downward.

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

Build pipeline (2.0, `builder.py` application layer). `docs/BUILD_LIFECYCLE.md` has the states.

```
server.py ──> builder.BuildManager ──> lifecycle (state machine, transitions recorded)
                 │  PREPARING: enhance backup+verify, staging copy, baseline tests; reuse.prepare (sandboxed pinned clones)
                 │  RUNNING:   sandbox.Run(claude -p …) egress = Claude API + package registries
                 │  VERIFYING: gates.run_all (sandboxed, no network) -> decide()
                 │  apply (enhance): manifest check -> renameat2(RENAME_EXCHANGE)
                 └─ launch: sandbox.Run(run.sh) + InboundForwarder (port only), health check, stop
sandbox.py:  bwrap command builder · EgressProxy (CONNECT allowlist, public IPs only) · InboundForwarder · self_test
sbx_init.py: runs INSIDE the sandbox: relays 127.0.0.1:3128 <-> egress socket, inbound socket <-> app port; execs the command
```

Analysis pipeline (2.0): `engine.analyze` = profile (Stage A) → providers in `sources.py` (plugins, GitHub, npm,
crates.io; Stage B) → lexical scoring with action-verb weighting (C) → README evidence for the top 5 (D) →
per-candidate evaluation and `decision.decide` (E). See docs/DISCOVERY_ENGINE.md.

Modules (dependencies point downward; stdlib only):
- presentation: `server.py`, `cli.py`, `static/`;
- application: `engine.py`, `builder.py`, `gates.py`, `reuse.py`;
- domain (pure): `textscore.py`, `policy.py`, `lifecycle.py`, `decision.py`;
- infrastructure: `sources.py`, `sandbox.py`, `sbx_init.py`, `history.py`, `obs.py`.

Trust boundaries: see docs/SECURITY_MODEL.md. The working directory and the tool allowlist are **not** the boundary;
the sandbox is.

Plugin: `.claude-plugin/plugin.json`, `skills/reusefirst/SKILL.md` (one skill: analyze, build, enhance, status),
`hooks/hooks.json` → `hooks/ensure_server.py` (SessionStart; starts the server detached if 5057 is free; refuses
non-Linux and Python < 3.11 with a message).
