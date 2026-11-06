# ReuseFirst — Reuse-First Builder (2.0)

Before you build an app from a requirement, ReuseFirst checks what already exists. It searches **Claude Code
plugins** (from the marketplaces installed on your machine), **GitHub repositories** and the **npm** and
**crates.io** registries. Each candidate gets:
- an *uncalibrated* relevance score;
- concept coverage;
- evidence confidence (higher when its README was inspected);
- licence class, compatibility and maintenance state;
- a recommendation: reuse, extend, borrow, build new, or *insufficient evidence*.

A reuse-or-build comparison then weighs effort ranges, assumptions and sensitivity.

The Build tab can create a new app, or enhance an existing app in `~/apps`, with Claude Code. Builds run inside a
sandbox and are **verified independently** by ReuseFirst before they count as successful. Every build follows two
bundled standards: UAISES for engineering and UEUIS for the UI.

## Install
`/plugin install reusefirst --marketplace buildsbeyondai-code/reusefirst` (Claude Code 2.1.275+), or
`/plugin marketplace add buildsbeyondai-code/reusefirst` then `/plugin install reusefirst@reusefirst`.

## Use
- `/reusefirst:reusefirst <requirement>` (or `status`), or just ask "does something like this already exist?".
- Web UI: http://127.0.0.1:5057/. It has three tabs: Analyze, Build app and Past requirements.
- Requires Linux or WSL2 with Python 3.11+ (standard library only). Builds also need the Claude Code CLI and
  **bubblewrap** (`sudo apt install bubblewrap`). Without a verified sandbox, builds are blocked; analysis still works.

## What this plugin runs, reads, sends and stores
Everything below is local to your machine unless stated otherwise.

**Runs**
- **SessionStart hook** (`hooks/ensure_server.py`): if nothing is listening on 127.0.0.1:5057 (`REQAN_PORT`), it starts
  the web UI as a background Python process bound to 127.0.0.1 only. It never blocks the session.
- **Sandbox self-test** at server start. Harmless probes check that the sandbox hides your home and credentials,
  blocks host localhost and direct network access, and drops capabilities.
- **Builds, only when you press Create app or Enhance app.** `claude -p … --permission-mode dontAsk --allowedTools
  <fixed list> --max-budget-usd <cap>` runs **inside bubblewrap**:
  - your home is an empty tmpfs, and only the app folder is writable;
  - there is no Docker socket, and all capabilities are dropped;
  - it has its own network namespace, so your localhost services are unreachable;
  - outbound HTTPS is allowed only to `api.anthropic.com`, `pypi.org`, `files.pythonhosted.org` and
    `registry.npmjs.org`, through a filtering proxy;
  - memory, process and CPU limits come from a systemd user scope where available.

  Your Claude credential file is mounted **read-only** into this one sandbox, because the agent cannot work without
  it. It uses your own Claude usage, up to the cap and time limit you set.
- **Reuse sources**: ReuseFirst (not the agent) clones the projects you tick, in a sandbox that can reach only
  github.com. Each clone is pinned to the exact commit, with no hooks and no submodules. Projects whose licence does
  not allow copying are not cloned.
- **Verification**: after the agent finishes, ReuseFirst re-runs the app's tests, a syntax check, a secret scan, an
  SBOM and licence checks, and a sandboxed start-up check. This runs in the sandbox with **no network**.
- **Enhance mode**: ReuseFirst takes a verified tar.gz backup and works on a staging copy. It swaps the copy in
  atomically, and only if every mandatory check passes and you did not change the app meanwhile.
- **Launch** starts a verified app inside the sandbox (no network), forwards only its port to 127.0.0.1, and offers
  Stop.

**Reads**
- The plugin catalogs of your installed Claude Code marketplaces (`~/.claude/plugins/`).
- A GitHub token, used only to raise GitHub's rate limits. It comes from `GITHUB_TOKEN` / `GH_TOKEN`, or else from
  `gh auth token`. Set `REQAN_NO_GH_CLI=1` to turn this off. The token is sent only to api.github.com, and it is
  never logged, stored or shown.
- The two standards: from `REQAN_UAISES` / `REQAN_UI_STANDARD`, else `~/.config/req-analyzer/config.json`, else the
  bundled `standards/`.

**Sends**
- **GitHub**: keywords from your requirement go to the GitHub search API. ReuseFirst also fetches the README of the
  top 5 repositories, as untrusted text. You can turn this off with "Search GitHub".
- **npm and crates.io**: the same keywords go to their search APIs.
- **OSV**: after a build, the generated app's dependency names and versions go to `api.osv.dev` for a
  known-vulnerability check. These are public package identifiers only.
- **Claude**: builds send your requirement and inputs to Claude through your own Claude Code CLI.

**Stores**
- Under `~/.local/state/req-analyzer/`:
  - `analyses/`: saved analyses (newest 500 kept);
  - `builds/`: build jobs, logs and verification results;
  - `backups/`: backups and previous versions;
  - `outcomes.jsonl`: build outcomes (numbers only);
  - `server.log`: JSON lines, with secrets redacted;
  - `session.token`: mode 0600.
- Nothing is uploaded, and there is no telemetry.

## Security
- The API is bound to 127.0.0.1 and checks the Host header (DNS-rebinding defence).
- It rejects cross-site Origin and Sec-Fetch-Site requests.
- Every `/api/*` route except `health` needs the session token. The token lives in a file only you can read.
- The browser receives the token only on same-origin requests. `REQAN_STRICT_TOKEN=1` turns `/api/session` off
  entirely and uses a `#token=` link instead.
- Request bodies need an explicit Content-Length up to 64 KiB. Slow clients time out after 15 s, and at most 32
  requests are handled at once.

See `docs/SECURITY_MODEL.md` in the repository.

Source, issues and full docs: https://github.com/buildsbeyondai-code/reusefirst · License: MIT
