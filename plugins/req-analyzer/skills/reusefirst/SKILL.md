---
name: reusefirst
description: ReuseFirst (Reuse-First Builder). Use before building a new app, tool, feature or Claude plugin from a requirement, when the user asks whether something "already exists", for "alternatives", "prior art" or "build or reuse", or when they want to build a new app or enhance an existing one with ReuseFirst, or check a ReuseFirst build. Finds the closest existing Claude plugins and GitHub projects with % closeness and a reuse verdict, and drives ReuseFirst's builds (new app or enhancement) at http://127.0.0.1:5057/.
argument-hint: <requirement text, a path to a requirements file, or "status">
allowed-tools: Bash(python3:*), Bash(curl -s http://127.0.0.1:5057/*), Bash(curl -s -X POST http://127.0.0.1:5057/*), Read
---

# ReuseFirst — Reuse-First Builder

Input: $ARGUMENTS (a requirement, a path to a requirements file, or "status"). If nothing was given, ask what the
app must do. If it is a path to an existing file, read it and use its contents as the requirement.

## 1. Analyze first (always, before building anything)
Pick 3–8 precise capability keywords: what the requirement must DO, not generic words like "app". Run:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/app" python3 -m reqanalyzer.cli --markdown -k "kw1" -k "kw2" "requirement text"
```
For long text, write it to a temporary file and pass `--file <path>`. Without `--markdown` the output is JSON with
`claude_plugins[]`, `github[]`, `verdict`, `best`, `errors` and `github_status`.

- Closeness is 75% IDF-weighted concept coverage + 25% TF-IDF cosine. It is lexical: before recommending reuse, check
  that the top 2–3 matches really do the job (open their links if needed), and say when they only share vocabulary.
- Verdicts: ≥70 reuse · 50–69 fork/extend · 30–49 borrow parts · <30 build new. Prefer candidates with a permissive
  license, recent activity and real adoption. State the gaps the user would still need to build.
- If `github_status` is `rate-limited` or `failed`, say so. Never invent repositories, stars or percentages the tool
  did not return.

Report in this order: the **verdict** with the single best candidate and why; a table of the top Claude plugins
(closeness %, name, what it covers, gaps); a table of the top GitHub repositories (closeness %, name, stars, license,
last update, gaps); and any warnings.

## 2. Build a new app, or enhance an existing one
Point the user to the web UI at http://127.0.0.1:5057/ (the plugin's SessionStart hook starts it):
- **1 · Analyze**: the same analysis, saved to **3 · Past requirements**.
- **2 · Build app**: in **Build into**, choose *A new app*, or *Enhance: <app>* for an app in `~/apps`. Then **List
  required inputs**: Claude pre-fills every UAISES input (users, journeys, MoSCoW features, Given/When/Then
  acceptance, non-functional targets, reuse picks). The user reviews them, sets the spending cap and time limit, and
  presses **Create app** or **Enhance app**. Claude Code then builds without asking questions, following the bundled
  UAISES and UEUIS standards. A new app gets `docs/COMPLETION_REPORT.md`. An enhancement backs up the app first, keeps
  its tests and coverage gate passing, and writes `docs/ENHANCE_REPORT.md`.

If the user asks you to start a build from the chat instead, use the local API. Show them the pre-filled inputs, the
spending cap and the time limit, and get their confirmation **before** starting, because a build spends their Claude usage:
1. `curl -s http://127.0.0.1:5057/api/apps` lists the apps that can be enhanced.
2. Get the token: `curl -s http://127.0.0.1:5057/api/session` (field `token`).
3. Inputs: `curl -s -X POST http://127.0.0.1:5057/api/inputs -H 'Content-Type: application/json' -H "X-ReqAn-Token: $TOKEN" -d '{"requirement": "...", "target": "<app path, or omit for a new app>"}'`
4. Start: `POST /api/build` with `{"requirement", "answers": {field id: value}, "labels": {field id: label}}` and the same headers.
5. Progress: `curl -s http://127.0.0.1:5057/api/builds/<id>?since=0`. Status `succeeded` / `failed` / `cancelled` /
   `timed-out`; `report` holds the report text.

## 3. "status"
`curl -s http://127.0.0.1:5057/api/builds` lists recent builds (status, cost, time).
`curl -s http://127.0.0.1:5057/api/analyses` lists past requirements. Summarise them in plain words.

Never restart the 5057 server while a build is running: the build would be marked interrupted.
