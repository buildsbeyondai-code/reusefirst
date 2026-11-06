# ReuseFirst — Reuse-First Builder (Claude Code plugin + local web UI)

Before building an app from a requirement, find what already exists: the closest **Claude Code plugins**
(every plugin in your installed marketplaces and the Claude plugin directory cache, ~3,600) and **GitHub
open-source repositories**, each with a **% closeness**, the concepts it does not cover, and a verdict
(Reuse ≥70 · Fork/extend 50–69 · Borrow parts 30–49 · Build new <30).

- Web UI: http://127.0.0.1:5057/ (SysPerf keeps 5056)
- In Claude Code: `/req-analyze <requirement>` or just ask "does something like this already exist?" (skill `requirement-analysis`)
- CLI: `PYTHONPATH=plugins/req-analyzer/app python3 -m reqanalyzer.cli --markdown "your requirement"`

## Build tab (2 · Build app)
1. **List required inputs**: every input needed to build the app, grouped by UAISES section (users, platforms, journeys,
   MUST/SHOULD/OPTIONAL, Given/When/Then acceptance, integrations, non-functional targets, architecture, delivery) plus
   app-specific questions, all pre-filled by Claude. The closest GitHub repos / Claude plugins are pre-ticked for reuse.
2. **Create app**: Claude Code builds it headless with no questions (`--permission-mode dontAsk`, fixed tool allowlist,
   spending cap, time limit) in `~/apps/<name>`: clones and reuses the ticked projects, follows UAISES (copied into the app's
   `docs/`), writes and runs tests, and finishes with `docs/COMPLETION_REPORT.md`, `docs/REUSE.md` and `run.sh`.
   Progress streams live; you can cancel; **Launch app** runs `run.sh`.
   **Build into** an existing app instead (any folder in `~/apps` with a CLAUDE.md, README.md or run.sh): the inputs are
   pre-filled from that app's own docs, a backup is taken first (`~/.local/state/req-analyzer/backups/`), the change is
   described in `docs/ENHANCE_SPEC.md`, existing tests and any `tools/coverage.sh` gate must keep passing, and the build
   ends with `docs/ENHANCE_REPORT.md`. Nothing is committed unless you tick it.
3. **UI standard**: every app with a user interface is built to the Universal Enterprise UI Standard (UEUIS): ISO 9241-110 interaction
   principles, WCAG 2.2 AA, every UI state, light and dark themes of equal quality, 320 px reflow. The level (Enterprise by
   default) is an input; the standard is copied into the app's `docs/` and the build refuses to start without it. The app
   must deliver `docs/UI_STATES.md`, `docs/ACCESSIBILITY.md` and the UEUIS §20 UI gate table in its completion report.

The analyzer's own UI meets UEUIS Enterprise, its §8 visual design system and the §8.11 rich patterns (status strip,
stepper, bullet graphs, band distribution, skeletons, toasts; see docs/DESIGN_SYSTEM.md) (brand app bar, KPI tiles, colour-coded
verdicts and status chips, icons): theme picker (follows the system, remembers Light/Dark), skip link, full
keyboard use, error summary, and loading, empty and error states (checked by `tests/test_ui_standard.py` and `tests/e2e_browser.py`).

## Install
In Claude Code:
```
/plugin marketplace add buildsbeyondai-code/reusefirst
/plugin install reusefirst@reusefirst
```
or from a shell: `claude plugin marketplace add buildsbeyondai-code/reusefirst && claude plugin install reusefirst@reusefirst`.
Requires Python 3.11+ (standard library only). Builds need the Claude Code CLI. The plugin's SessionStart hook starts the web
UI at http://127.0.0.1:5057/ if the port is free; optional always-on autostart: `tools/req-analyzer.service`.
For a working copy: `git clone https://github.com/buildsbeyondai-code/reusefirst && claude plugin marketplace add ./reusefirst`.

### Standards
Builds follow two standards, both bundled in `plugins/req-analyzer/standards/`: the Universal AI Software Engineering
Standard (UAISES) and the Universal Enterprise UI Standard (UEUIS). To use your own copies, set `REQAN_UAISES` /
`REQAN_UI_STANDARD`, or put `{"uaises": "<path>", "ui_standard": "<path>"}` in `~/.config/req-analyzer/config.json`.

## How closeness is computed (honest limits)
`closeness = 75% IDF-weighted concept coverage + 25% TF-IDF cosine` over name, description (first 350 chars) and topics,
with stemming and software synonyms. It is **lexical**, not semantic: two projects that describe the same thing in
different words score low, and a project that shares vocabulary but does something else can score high. The Claude
command/skill therefore reviews the top hits semantically before recommending. GitHub search without a token is limited to
10 searches/min (5 per analysis); set `GITHUB_TOKEN`, or the analyzer uses `gh auth token` if gh is logged in.

Requirements: Python ≥3.10, no third-party packages.
