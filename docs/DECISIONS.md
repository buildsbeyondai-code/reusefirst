# Decisions

- **D1 Stdlib only, single process.** Tiny workload, single user; no dependency or supply-chain surface, nothing to lock. A framework would add install steps to a plugin.
- **D2 Lexical scoring, semantic review by Claude.** Deterministic, offline-testable, free, explainable (shows matched/missing concepts). Embeddings would need a model download or a paid API. Probabilistic judgement stays in the Claude layer (UAISES §13). Weights 75/25 favour coverage because a user asks "how much of my requirement does it do".
- **D3 Descriptions clipped to 350 chars.** Repos that paste whole documents into the description matched every concept by accident (observed 70% for an unrelated whitepaper).
- **D4 Port 5057.** 5056 is SysPerf. Bound to 127.0.0.1; reachable from Windows via WSL2 localhost forwarding (verified).
- **D5 Autostart via plugin SessionStart hook, not systemd.** No always-on resident process; the server starts when Claude Code starts. An opt-in user unit is provided in `tools/` (installing it needs the user's go-ahead).
- **D6 Inner loop = full suite.** The suite runs in ~7 s, so an affected-test selector (UAISES §6) would add complexity without saving time. Revisit if it exceeds 60 s.
- **D7 GitHub token from env or the user's own `gh auth token`.** Raises the limit from 10 to 30 searches/min; never logged or returned.
- **D8 Builds run headless Claude Code in `dontAsk` mode.** "No questions" without `bypassPermissions`: anything outside the allowlist is refused, not prompted. Refusal count is shown per build.
- **D9 Input generation uses Claude with no tools and a JSON schema**, so the form is structured and cannot trigger actions; standard fields are always present so the form works if Claude fails.
- **D10 Reuse is pre-ticked, not forced.** Closest GitHub repo and plugin are always ticked (plus up to 3/2 more ≥30%); the build decides base vs borrowed parts after reading licenses, and records it in docs/REUSE.md. No license → learn only, no copying.
- **D11 UAISES is mandatory for builds.** Copied into each app's docs/; build refuses if unreadable. §2 fields (users, platforms, journeys, must-haves, acceptance) are required.
- **D12 One build at a time.** 7.8 GB host; parallel builds would compete for RAM and API budget.
