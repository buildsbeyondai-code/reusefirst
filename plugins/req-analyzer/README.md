# ReuseFirst — Reuse-First Builder

Before you build an app from a requirement, ReuseFirst checks what already exists. It lists the closest **Claude Code
plugins** (from the marketplaces installed on your machine) and **GitHub open-source repositories**, each with a %
closeness score and a verdict: Reuse ≥70 · Fork/extend 50–69 · Borrow parts 30–49 · Build new <30. Its Build tab can then
create a new app, or enhance an existing app in `~/apps`, with Claude Code. Every build follows two bundled standards:
the Universal AI Software Engineering Standard (UAISES) for engineering, and the Universal Enterprise UI Standard (UEUIS)
for the UI.

## Use
- `/req-analyze <requirement>`, or ask "does something like this already exist?" (skill `requirement-analysis`).
- Web UI: http://127.0.0.1:5057/. It has an Analyze tab, a Build app tab (a new app or an existing one) and Past requirements.
- Requires Python 3.11+ (standard library only). Builds need the Claude Code CLI.

## What this plugin runs, reads, sends and stores
Everything below is local to your machine unless stated otherwise.

**Runs**
- **SessionStart hook** (`hooks/ensure_server.py`): if nothing is listening on 127.0.0.1:5057 (`REQAN_PORT`), it starts
  the web UI as a background Python process bound to 127.0.0.1 only. It never blocks the session.
- **Build tab, only when you press Create app or Enhance app**: it runs
  `claude -p … --permission-mode dontAsk --allowedTools <fixed list> --max-budget-usd <cap>` in the chosen app folder.
  The tool list is fixed (`BUILD_TOOLS` in `app/reqanalyzer/builder.py`). It includes file edits, python, pip, npm,
  git (clone, add, commit; no push), WebSearch and WebFetch. Anything else is refused without a prompt. This uses your
  own Claude Code account and usage, up to the spending cap and time limit you set. It does **not** change your Claude
  Code permission settings: the flags apply only to that one child process.
- **Enhance mode**: before a build changes an existing app, it saves a tar.gz backup of that app to
  `~/.local/state/req-analyzer/backups/`. Virtual environments, caches and browser profiles are left out.
- **Inputs step**: runs `claude -p` once with no tools to pre-fill the build form from your requirement.

**Reads**
- The plugin catalogs of your installed Claude Code marketplaces (`~/.claude/plugins/`).
- A GitHub token, used only to raise GitHub's search rate limit. It comes from `GITHUB_TOKEN` / `GH_TOKEN`, or else from
  `gh auth token` (the GitHub CLI, also tried through Windows PowerShell under WSL). Set `REQAN_NO_GH_CLI=1` to turn
  this off. The token is sent only to api.github.com, and it is never logged, stored or shown.
- The two standards: from `REQAN_UAISES` / `REQAN_UI_STANDARD`, else `~/.config/req-analyzer/config.json`, else the
  copies bundled in `standards/`.

**Sends**
- Search keywords taken from your requirement go to the GitHub search API (`https://api.github.com/search/repositories`),
  unless you untick "Search GitHub". Nothing else is sent anywhere by the analyzer.
- Builds send your requirement and build inputs to Claude through your own Claude Code CLI. During a build, Claude may
  clone the public GitHub repos you ticked for reuse, and search or fetch the web.

**Stores**
- Saved analyses: `~/.local/state/req-analyzer/analyses/` (the newest 500 are kept; delete any of them in the UI).
- Build jobs and logs: `~/.local/state/req-analyzer/builds/`. Backups: `~/.local/state/req-analyzer/backups/`.
- Server log: `~/.local/state/req-analyzer/server.log`. Nothing is uploaded, and there is no telemetry.

## Security
The web UI binds to 127.0.0.1 only and checks the Host header. Writes need a per-session token. Builds may only write
inside your home folder. They are never placed in `~/.claude`, `~/.config`, `~/.ssh` or `~/.local`, or inside the
plugin itself.

Source, issues and full docs: https://github.com/buildsbeyondai-code/reusefirst · License: MIT
