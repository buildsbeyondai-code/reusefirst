# Changelog

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
