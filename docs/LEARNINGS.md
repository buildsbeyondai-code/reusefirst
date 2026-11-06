# Learnings

Fast loop: `python3 -m unittest discover -s tests` (74 tests, ~12 s; uses fixture catalogs + a fake GitHub server, no network).
Browser E2E (real catalog + real GitHub, needs the server running):
`<any Python with Playwright + Chromium> tests/e2e_browser.py http://127.0.0.1:5057/ <screenshot dir>`

| Change | Where |
|---|---|
| Stop words, synonyms, scoring weights, verdict bands | `app/reqanalyzer/textscore.py` |
| New data source / GitHub behaviour | `app/reqanalyzer/sources.py` |
| Query strategy, limits, result shape | `app/reqanalyzer/engine.py` |
| HTTP routes, security | `app/reqanalyzer/server.py` |
| UI | `app/reqanalyzer/static/` (restart server after editing) |
| Saved analyses (history, retention, ids) | `app/reqanalyzer/history.py` |
| Build inputs, allowlist, prompts, job lifecycle | `app/reqanalyzer/builder.py` |
| Build tab UI | `static/app.js` (bottom half), `static/index.html` `#panel-build`. One shared `#req` textarea above the tabs feeds both tabs |
| What Claude does with results | `skills/reusefirst/SKILL.md` (the only skill/command) |

Timings (2026-11-02): cold analysis with GitHub ~10 s (5 queries, unauthenticated); cached repeat 0.04 s; catalog load 3,666 plugins <1 s.

Build tests use `tests/fake_claude.py` (FAKE_CLAUDE_MODE ok|fail|crash|slow|inputs-error|inputs-garbage). Real build E2E (spends usage):
`tests/e2e_build.py <url> <shots-dir> "<requirement>"` via the SysPerf venv Python.
Live timings: input listing ~35 s (real Claude).

| Icons | SVG sprite at the top of `static/index.html` (`<symbol id="i-…">`), `icon(name)` in app.js |
| Colours for verdicts, scores, build status | `band()`, `statusChip()` in app.js; tokens in app.css (no hex literals outside token blocks, a test enforces it) |
| UI standard rules / theme tokens | `static/app.css` tokens (checked by `tests/test_ui_standard.py`), `builder.ui_instructions()` for builds |

Traps:
- A flex-column body (sticky footer) shrinks `margin: 0 auto` wrappers to their content: keep `.wrap { width: 100% }`.
  e2e_browser.py asserts the requirement box spans the viewport.
- A `.sr-only` span (position:absolute) inside a scrolling table escapes to the page and causes sideways scroll at 320-390 px
  unless an ancestor is positioned: `.tw`, `th`, `td` have `position: relative`.
- The theme is set by `/theme.js` in <head> (CSP forbids inline scripts) so a chosen theme never flashes.
- `claude -p` waits 3 s for stdin unless stdin is /dev/null (DEVNULL in code).
- Claude adds app-specific questions that duplicate standard fields (port, theme): filtered by STANDARD_TOPICS.
- The server must be restarted after Python changes (no autoreload).
- Ports 5060/5061 (SIP) and other Chromium "restricted ports" give ERR_UNSAFE_PORT: curl works, browsers refuse. Found by the
  real build E2E; free_port() starts at 5070 and validate_spec rejects BROWSER_UNSAFE_PORTS.
- dontAsk allowlist patterns match the literal command: Claude often uses absolute paths (/abs/.venv/bin/pip, /abs/run.sh), so
  build_tools() adds absolute forms. WSL has no git identity: builds get GIT_AUTHOR_*/GIT_COMMITTER_* env (REQAN_GIT_NAME/EMAIL).
- First real build (water tracker, 2026-11-02): 7.9 min, $2.41, 38 tests, honest REUSE.md; 9 refusals (fixed above).
- Don't lowercase-split camelCase: "GitHub" became "git hub".
- Never send stems to GitHub ("recurr" misses "recurring"); use `surface_map`.
- `pkill -f "reqanalyzer.server"` from a Bash tool call also kills the calling shell (its command line matches). Kill by PID from `ss -ltnp`.
- Unauthenticated GitHub search = 10/min → two analyses per minute.
- Unit tests passing did not catch `[object Object]%` in the UI; the browser E2E now asserts numeric percentages.
- The CSP (`style-src 'self'`, no unsafe-eval) blocks inline `style="..."` attributes in index.html, and blocks Playwright's
  string `wait_for_function`. Use CSS classes, and `wait_for_selector` with `:text()` in E2E scripts.
- e2e_browser.py writes real entries into the saved-analysis history; delete them after a test run.

- Enhance mode (1.12): a build can target an existing app in the apps folder (`existing_apps()`). It backs the app up first (tar.gz in the state dir, without venvs, clones or browser profiles), writes docs/ENHANCE_SPEC.md (the app's own BUILD_SPEC.md is kept), and reads docs/ENHANCE_REPORT.md. A new build still refuses non-empty folders.
- Standards lookup: env var, then `~/.config/req-analyzer/config.json` (`uaises`, `ui_standard`), then the copies bundled in `plugins/req-analyzer/standards/`. On the author's PC the config points at the live OneDrive files. Re-copy the bundled files before each release.
- Never restart the 5057 server while a build is running: the build is marked interrupted.
- The SessionStart hook runs from the installed plugin cache (~/.claude/plugins/cache/reusefirst/reusefirst/<version>), not from the working copy. After changing code, bump the version and run `claude plugin update reusefirst@reusefirst`, or the next session starts the old cached server. Until 1.12 the cache was still 1.0.0.
- 1.13: one skill only (`skills/reusefirst`). A plugin with both a command and a skill shows as two entries in the `/` menu, which users read as two plugins.
