# Project state — 2026-11-06 (v2.1.0)

Done:
- v1.0: analyzer, Analyze tab, CLI, Claude plugin (command, skill, SessionStart hook), local marketplace; installed (user scope).
- v1.1: Build tab — lists all inputs required to build the app (UAISES-grouped, Claude pre-filled, app-specific questions),
  reuse checklist with the closest GitHub repos and Claude plugins pre-ticked, non-interactive build via headless Claude Code
  (dontAsk + allowlist + budget + time limit), live progress, cancel, launch, recent builds. UAISES mandatory for every build.
- v1.2 (2026-11-05): one shared Requirement box above both tabs (no separate Build requirement). Every Analyze run is
  saved with a timestamp to ~/.local/state/req-analyzer/analyses/<UTC ms id>.json (newest 500 kept); "Previous analyses"
  table on the Analyze tab with Open (restores requirement, keywords, GitHub flag and results) and Delete (session token).
  API: GET /api/analyses, GET /api/analyses/<id>, POST /api/analyses/<id>/delete.
- v1.3 (2026-11-05): UEUIS (OneDrive OPEN SOURCE/UNIVERSAL_ENTERPRISE_UI_STANDARD.md, env REQAN_UI_STANDARD) integrated.
  Builds: copied into each app's docs/, mandatory like UAISES, new input "UI standard conformance level" (Enterprise default),
  build prompt requires §1-§17 and the §20 UI gate table; CLI/REST/No-UI apps get the reduced form. The analyzer UI itself
  was brought to UEUIS Enterprise (theme picker + theme.js, tokens checked by tests/test_ui_standard.py, skip link, error
  summary, §6 states, named confirmations, forced colours, reduced motion). 84 unit tests + browser E2E pass.
- v1.4 (2026-11-05): visual redesign to UEUIS v1.1 §8 (colour roles, type scale, formats): brand gradient app bar with
  logo and standard badges, overlapping requirement card, segmented tabs with icons, verdict banner coloured by score band,
  KPI tiles (best match, verdict, plugins, repos, time), coloured chips (verdict, build status, tags), tinted table headers
  with row hover, empty states with icons, colour-striped build fieldsets, console-style progress log, footer badges.
  One SVG icon sprite in index.html. 86 unit tests + browser E2E pass in light and dark.
- v1.5 (2026-11-05): UEUIS v1.2 §8.11 rich patterns, in this tool's own identity (§8.13; not SysPerf's glass/ring look):
  system status strip from /api/health (server, catalog, GitHub auth, Claude CLI, standards, build; refreshed every 30 s
  with freshness), workflow stepper, bullet graphs (Few) for every score with 30/50/70 bands and a 70% target tick, one
  score mapping everywhere (70/50/30), matches-by-band stacked bar, skeleton loading, toasts, relative + absolute times,
  copy buttons for folder paths. /api/health gained claude_cli, github_authenticated, standard_found, ui_standard_found,
  build_running.
- v1.6 (2026-11-05): fixed "light and dark look the same" (the brand header was identical in both): per-theme header
  tokens (light lavender band, deep-night band), brand kept as a 4 px accent strip and logo. UEUIS v1.3 §8.14 top-20 polish:
  segmented theme switcher, calm status summary (ISA-101), badges moved to footer, sticky tabs + stepper, display type,
  first-run examples, character counter + Ctrl+Enter, busy buttons, results filter (/), 3-line clamp + Show more, source
  avatars + owner/name, compact stars + relative dates + licence chips, gap chips, verdict next-step actions, mobile cards,
  favicon + live document title, print stylesheet, footer version/shortcuts, [hidden] always wins. Builds now must
  follow §8.9 distinct themes, §8.13 identity and §8.14.
- v1.7 (2026-11-05): richer light theme (mesh header, gradient title, gradient primary buttons, tinted tiles/verdict,
  tinted shadows, page glow); fewer buttons (UEUIS §8.15): icon-only theme switcher, status pill toggles its own details,
  examples as text links, history row title opens it + trash icon, copy icons, duplicate "Build this app" removed;
  laptop density (UEUIS §9.1): 1480 px content width, 24 px gutters, compact rhythm, slimmer header under 900 px tall.
- v1.8 (2026-11-05): multi-colour palettes per theme (UEUIS v1.5 §8.16): Sunrise (light) and Aurora (dark), three-stop
  brand/title/action gradients, teal/mint accent, five categorical colours on sections, tiles, avatars and form groups.
- v1.9 (2026-11-05): enterprise restyle (UEUIS v1.6 §8.16-§8.19): solid Slate & Teal / Graphite & Mint palettes, no
  gradients/glows, compact header, underline tabs; Descriptions switch (hidden by default); History as its own tab;
  keywords box and stepper removed; requirement box fills the free height; footer pinned to the bottom.
- v1.10 (2026-11-05): frameless, full-width requirement box (16 px gutters, ~500 px tall at 1366x768); fixed wrappers
  shrinking to content after the flex-column body change (.wrap width 100%).
- v1.11 (2026-11-05): tab bar moved to the top under the header; History renamed "3 · Past requirements".
- Real build verified: ~/apps/water-intake-tracker (38 tests pass when re-run; works in a browser on 5070).
- Tests: 74 unit/integration (fake claude, fake GitHub); browser E2E for Analyze; real build E2E (tests/e2e_build.py).
- Repo initialised, nothing committed (user has not asked).

- v1.12 (2026-11-06): Build into an existing app (enhance mode: /api/apps, inputs target, backup, ENHANCE_SPEC/REPORT,
  enhancement prompt keeping existing tests and coverage gates). Standards bundled (plugins/req-analyzer/standards/) with
  env → ~/.config/req-analyzer/config.json → bundled lookup. Prepared for publishing as a public plugin marketplace
  (marketplace name req-analyzer, GitHub buildsbeyondai-code/req-analyzer). 106 unit tests + browser E2E pass.
- v1.12.1–1.12.2: renamed to ReuseFirst (Reuse-First Builder); plugin/marketplace `reusefirst`, public repo
  github.com/buildsbeyondai-code/reusefirst. 1.12.3: plugin README with full disclosure + LICENSE (directory-ready).
- v1.13.0: the `/req-analyze` command and the `requirement-analysis` skill merged into ONE skill `reusefirst`
  (analyze, build/enhance via the UI or API with user confirmation, status), so the plugin shows one entry.

- v2.0.0 (2026-11-06): the 9.8+ hardening programme (OneDrive OPEN SOURCE/REUSE FIRST/ReuseFirst_9_8_Plus_Master_Prompt.md).
  - **Security:** bubblewrap sandbox with egress allowlist proxy, failing closed; token on every API route; strict
    validation.
  - **Reuse:** reuse policy, pinned clones and provenance; SBOM and OSV checks.
  - **Builds:** state machine, independent verification gates, transactional enhancement, sandboxed launch with Stop.
  - **Discovery:** multi-stage discovery (npm, crates.io, README evidence) with a reuse-vs-build decision; labelled
    benchmark.
  - **Quality:** 188 tests, 90% coverage, mutation 16/16, CI.
  - Audit: docs/AUDIT_BASELINE.md (before) and docs/FINAL_AUDIT.md (after).

- 2.0.1–2.1.0 (2026-11-06), from the first real enhancement build (job finder unattended mode):
  - Fixed: skipped tests counted as passed; the claude symlink not mounted (exit 127); "success" shown as the reason
    for a usage-limit stop.
  - Added: Playwright toolchain mount; user data and secrets kept out of builds; nested Bash sandbox denying the
    credential; same-user API check; resume; optional semantic review.
  - CI passes on GitHub (Python 3.11/3.12/3.14 + mutation).

Open / next:
- A real end-to-end build with real Claude inside the 2.0 sandbox (spends usage; needs user approval).
- Live A/B value benchmark (`tools/value_benchmark.py --i-accept-cost`), and independent human relevance labels.
- Semantic re-ranking (D21); calibration once outcome data exists.
- Optional always-on autostart (`tools/req-analyzer.service`) — needs user approval.
- Optional semantic re-ranking for the Analyze tab.
