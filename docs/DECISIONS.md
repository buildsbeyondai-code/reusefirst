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

## 2.0 (2026-11-06)
- **D13 bubblewrap over containers.** Rootless Podman or Docker is not installed on the target (WSL2) and would add a
  daemon or a large dependency. bubblewrap is a single setuid-free binary in Ubuntu's main archive, and it gives
  every namespace. The network namespace plus a host-side allowlisting CONNECT proxy gives per-host egress without
  iptables or root.
- **D14 Fail closed, with no override.** No env var re-enables host execution. A "temporary" escape hatch would
  become the default, and would cap the rating (unsafe fallback).
- **D15 The Claude credential is mounted read-only into the build sandbox only.** The agent cannot run without it.
  Alternatives (proxying the API with injected auth) depend on undocumented CLI behaviour. The residual risk is
  documented, and the secret-scan gate partially mitigates it.
- **D16 ReuseFirst clones, not the agent.** Clones run with GitHub-only egress at a pinned commit, licence-checked
  before the agent sees them. This moves supply-chain decisions out of the LLM.
- **D17 Gates decide success.** `succeeded` = all mandatory gates VERIFIED. When something cannot be checked
  (offline OSV, no node for JS), the result is NOT VERIFIED, reported as `partially_completed`, never silently passed.
- **D18 Staging copy mounted at the real path.** Enhancements build in a sibling staging folder bind-mounted at the
  app's path inside the sandbox, so venv shebangs and absolute paths work. The atomic swap uses
  renameat2(RENAME_EXCHANGE).
- **D19 Effort in relative units.** The decision engine does not output hours or money (false precision). Ranges,
  assumptions and sensitivity are shown instead.
- **D20 Action-verb weighting.** Measured on a labelled benchmark (NDCG@10 0.740 → 0.763). Name double-counting was
  tried and rejected (0.717). The verb list was not tuned after evaluation.
- **D21 No semantic model.** Embeddings would need a model download (hundreds of MB) or a paid API. The engine stays
  lexical and labels its confidence as reduced. The provider and decision interfaces leave room for a semantic
  re-ranker.
- **D22 PyPI is not a provider.** PyPI has no supported search API (XML-RPC search is disabled), and scraping HTML is
  brittle.
