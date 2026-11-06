# Changelog

## 2.1.1 — 2026-11-06
Found by the real job-finder enhancement, which ended `partially_completed` with "no port configured":
- **Start-up check finds the app's port.** The launch gate reads the port variable from `run.sh` or the source
  (`os.environ.get("X_PORT", "5070")`, `${X_PORT:-N}`, `process.env.X_PORT || N`). When that port is busy, for
  example because your own copy is running, it checks on a free port.
- **Verify again** (`POST /api/builds/<id>/verify`, plus a button): re-runs only the gates on a partially completed
  build's finished work. No agent runs and no Claude usage is spent, and the work is applied if every mandatory gate
  passes.
- **Leftover cleanup:** the empty `.claude/` mount-point folder that Claude Code's Bash sandbox leaves in the project
  is removed before applying. Folders with real files are kept.

## 2.1.0 — 2026-11-06
- **Resume:** a failed, timed-out, interrupted or cancelled build continues from the work it already did
  (`POST /api/builds/<id>/resume`, plus a **Resume build** button).
  - Enhancements copy the earlier attempt's staging folder and keep the original app's baseline tests.
  - New apps continue in the same folder.
  - The agent is told to inspect and finish, not start over.
- **Truthful failure reasons:** a usage-limit stop now reads "Claude usage limit reached (5-hour limit, resets …)",
  not "success" (found in a real build). Spending cap, turn limit and missing-result cases are distinguished.
- **Optional semantic review ("Deep check with Claude"):** a sandboxed, tool-less review of the top 8 candidates
  (see docs/DISCOVERY_ENGINE.md).
- **Same-user API check** (peer uid from /proc/net/tcp; other local accounts are refused).
- **Inputs prefill runs in the sandbox.** Stop words were added for long requirements, and capability estimates
  diminish for long requirements.

## 2.0.2 — 2026-11-06
- **Fixed (found by the first real build):** Claude was launched through the `~/.local/bin/claude` symlink, which
  is not mounted in the sandbox, so the build exited 127. ReuseFirst now launches the real binary path, with a
  regression test.
- **The credential is no longer readable by generated code.** Every Bash command the agent runs (tests, scripts,
  installs) now runs in Claude Code's own nested sandbox, set through the documented `--settings`:
  - `sandbox.enabled` with `failIfUnavailable` and no unsandboxed retry;
  - `credentials.files` / `filesystem.denyRead` cover `~/.claude/.credentials.json` and `~/.claude.json`;
  - network is limited to the package registries;
  - `Read(...)` deny rules block the credential, and `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` is set.

  Verified with a decoy secret: a sandboxed `open()` raises PermissionError. Builds are blocked if `socat` (needed
  by that sandbox) is missing.

## 2.0.1 — 2026-11-06
Found by the first real enhancement of a Playwright-based app (the job finder):
- **Skipped tests no longer count as passed.** The test gate reports `skipped`, and a new advisory gate,
  `skipped_tests`, marks what they cover as NOT VERIFIED. 1.x and 2.0.0 counted the 6 skipped browser tests as
  passes.
- **Browser tests run in the sandbox.** Read-only, non-secret toolchains (Playwright's browsers in
  `~/.cache/ms-playwright`, overridable with `REQAN_SANDBOX_TOOLCHAIN`) are mounted, so Chromium-based tests run
  during builds and verification instead of being skipped.
- **User data and secrets never enter the build.** `data/`, `.env`, `browser-profile/` and `secrets/` are kept out
  of the enhancement staging copy. The agent cannot read them, so it cannot send them to the model API or change
  them. They are carried over unchanged at the atomic swap, with crash recovery. App data written during a build is
  no longer a conflict; only code edits block the swap.

## 2.0.0 — 2026-11-06 (major: security model and API changes)
### Security (breaking)
- **Builds run in a bubblewrap sandbox:**
  - all namespaces unshared, capabilities dropped, environment cleared;
  - HOME is an empty tmpfs, and only the project folder is writable;
  - private network namespace, with HTTPS egress only to allowlisted hosts through a filtering proxy (public IPs
    only);
  - systemd-scope memory, task and CPU limits; process-tree cleanup.

  Reuse clones, test re-runs and launched apps are sandboxed too. **Fail closed:** without a verified sandbox,
  builds are blocked.
- **The API needs the session token on every `/api/*` route** except `/api/health` and `/api/session`.
  - The token file is `~/.local/state/req-analyzer/session.token` (0600).
  - `/api/session` serves the browser on same-origin requests only. Strict mode is `REQAN_STRICT_TOKEN=1`.
  - Cross-site Origin and Sec-Fetch-Site requests are refused.
  - Content-Length is required (≤ 64 KiB, no negatives or chunked bodies), sockets time out after 15 s, and at most
    32 requests run at once.
- **Strict input validation:**
  - finite, range-checked budget, time and port (NaN, inf and bool rejected instead of clamped);
  - structural GitHub URL parsing for reuse (no substring matching);
  - TOCTOU re-checks of output folders; symlinked apps excluded.
- **Reuse policy:**
  - nothing is pre-ticked by rank alone; deterministic SPDX licence rules;
  - ReuseFirst clones at a pinned commit, removes non-copyable sources, and writes `docs/REUSE_PROVENANCE.md`;
  - every build gets a CycloneDX SBOM and an OSV vulnerability check.
- Secret redaction in logs, build events and diagnostics. Logs are structured JSON.
### Reliability
- Explicit build state machine (created → … → succeeded / partially_completed / failed / cancelled / timed_out /
  interrupted / blocked).
- **Independent verification gates.** `succeeded` now means every mandatory gate passed, not "Claude exited 0".
- Transactional enhancement:
  - a verified backup, then work on a staging copy with baseline tests and a regression gate;
  - change detection, so nothing is applied if you edit the app mid-build;
  - an atomic `renameat2` swap, with journaled recovery.
- Cancel works in every active state. Orphans are killed on restart only when the PID's start time matches.
  `Idempotency-Key` stops duplicate builds.
- Launch runs in the sandbox with a health check and port forwarding, and has a new **Stop** control
  (`POST /api/builds/<id>/stop`).
### Discovery
- Multi-stage pipeline:
  - requirement profile (languages, platforms, integrations);
  - npm and crates.io providers;
  - README evidence for the top GitHub candidates;
  - per-candidate coverage, evidence confidence, licence class, compatibility, maintenance and recommendation
    (including *insufficient evidence*);
  - a reuse-vs-build decision with effort ranges, assumptions and sensitivity, plus an exportable report
    (`/api/analyses/<id>/report.md`);
  - measured outcomes (`/api/outcomes`).
- Provider-scoped ids: same-named plugins from different repositories no longer collide. Bounded LRU cache with
  freshness. Deterministic tie-breaks. Action-verb weighting (labelled benchmark NDCG@10 0.740 → 0.763).
- The % is labelled *relevance (uncalibrated)* everywhere.
### Fixed
- Python 3.11 compatibility: an f-string in the inputs prompt only parsed on 3.12+.
### Tooling
- 188 tests: security, sandbox and seeded fuzz/property tests, gates, decision, benchmark.
- Branch coverage 90%. ruff and bandit clean. Mutation check 16/16.
- GitHub Actions CI with SHA-pinned actions.
### Migration
See docs/MIGRATION_2.0.md.

## 1.13.0 and earlier
One `reusefirst` skill, the ReuseFirst rebrand, enhance mode, the UEUIS UI standard, the Build tab and the initial
analyzer. See `git log`.
