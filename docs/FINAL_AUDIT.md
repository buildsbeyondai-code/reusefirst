# Final audit (Phase 12) — ReuseFirst 2.1.1

**Audited:** 2026-11-06 (re-scored after the first real builds). Start commit `76d9cb2` (1.13.0). End: `main` at
2.1.1.

**Method:** each claim below was checked against code, a test, CI or a real run in this session. Where something
was not run, it says **NOT VERIFIED**. The rubric and caps are unchanged.

## Evidence summary
| Check | Result |
|---|---|
| Unit, integration, security, sandbox, fuzz, recovery and benchmark tests | **221 tests OK** (39.7 s) |
| Coverage (branch) | **92%** overall; **92%** for the critical core (sandbox, server, policy, lifecycle, gates, reuse, builder, semantic) |
| GitHub Actions CI | **passing** on Python 3.11, 3.12 and 3.14 on ubuntu-24.04 (sandbox self-test on a clean runner, ruff, bandit, coverage ≥ 85%, benchmark, packaging, SBOM, pip-audit) plus the mutation job |
| Mutation check | **22/22 killed** (two equivalent mutants documented) |
| ruff / bandit (medium+) | clean / 0 findings |
| Sandbox self-test | 13/13 probes |
| Nested agent Bash sandbox | a decoy secret under `denyRead` raises PermissionError; `/proc/1/environ` blocked; pypi reachable |
| Retrieval benchmark (12 queries, assistant labels) | NDCG@10: v1 0.740 → v2 0.763 → v2 + semantic review **0.908** (circular labels) |
| Browser E2E (Chromium) | PASS: light/dark, 390/320 px, forced colours, keyboard, decision panel, packages |
| **Real end-to-end enhancement build** | **VERIFIED** (details below) |
| Live install | 2.1.1 on 5057; sandbox ok; 403 without the token, 403 for other OS users |
| Product value A/B (with vs without ReuseFirst) | harness ready; **live runs NOT VERIFIED** (paid) |
| Firefox / WebKit | out of scope by the user's decision (Chrome only) |

## The real build: job finder "unattended auto-apply" (2026-11-06)

| Attempt | Outcome | What ReuseFirst learned or fixed |
|---|---|---|
| 1 | FAILED in PREPARING+RUN (exit 127), $0 | Claude was launched via the symlink path, which is not mounted → launch the real binary (2.0.2) |
| 2 | FAILED: Claude usage limit after 24 min, $6.37; app untouched | Reason shown as "success" → truthful classification; **Resume** added (2.1.0) |
| 3 (resume) | PARTIALLY_COMPLETED: 120/120 tests (0 skipped), regression and OSV VERIFIED; launch NOT VERIFIED; app untouched | Enhance builds had no port → port detection and a free-port check; **Verify again** (2.1.1) |
| 4 (verify again, no agent) | **SUCCEEDED**, applied atomically, $0 | Every mandatory gate VERIFIED; launch HTTP 200 via `RMJF_PORT`; `.claude/` leftover stripped; user data and login profile carried over intact |

Earlier fixes from the same app (2.0.1):
- 6 browser tests had been skipped, and the old parser counted them as passed.
- Playwright browsers are now mounted.
- The user's `data/`, `.env` and browser login profile are now kept out of the agent's view.

**Totals:** about $10.37 (model-reported) across the attempts. The final app is 92 → 120 tests. It was restarted on
5070, and the Unattended screen renders in Chromium with no page errors.

**What this proves:**
- The pipeline fails safely: four outcomes, and the user's app was never left half-changed.
- It reports truthfully.
- The recovery features work in real conditions.

## Remaining limitations
1. **Discovery is lexical unless the paid semantic review is ticked.** Every benchmark label is assistant-made (12
   queries, plugin corpus). GitHub, npm and crates.io ranking is not benchmarked. Scores are uncalibrated.
2. **Product value is not measured.** Whether ReuseFirst saves time or money in practice is NOT VERIFIED; the A/B
   harness exists.
3. **Installs and code share a phase.** The agent's dependency installs run in the same sandboxed phase as generated
   code. Egress is limited to package registries, but installation and execution are not separated.
4. **The agent can read the credential.** The agent process itself can still read the Claude credential (required).
   Generated code cannot.
5. **Windows-side access.** Requests from Windows arrive through WSL's root-owned relay, so other Windows users of
   the same PC are not distinguished.
6. **Unchecked code paths.** JS/TS syntax is unchecked (no Node in the verifier). The static-analysis gate is
   advisory and needs the project's own ruff.
7. **Allowlist friction.** The agent's compound shell commands (`a; b`, `$?`) are refused by the dontAsk allowlist.
   It retries with simpler commands, which costs turns.
8. **Coverage short of target.** 92% against the programme's 95% statement target for the core.
9. **No independent security review** or production reliability data.

## Score (programme rubric, unchanged)
| Category | Weight | Score | Basis |
|---|---:|---:|---|
| Security and supply-chain safety | 20 | 18.0 | Two-layer sandbox, credential denied to generated code (decoy-verified), same-user API, fail-closed, SBOM/OSV, licence policy. Minus 3–5 and no independent review |
| Functional correctness and reliability | 15 | 13.5 | Real enhancement verified end to end; the state machine, resume, verify-again, atomic swap and crash recovery are all exercised. Minus no long-run reliability data |
| Discovery and matching intelligence | 15 | 11.0 | Multi-provider, README evidence, semantic review, decision engine, measured gains. Minus 1 |
| Autonomous build quality | 15 | 13.0 | Independent gates decided a real build correctly, including a true partial. Minus 6–7 |
| Testing and independent verification | 15 | 13.0 | 221 tests, CI green on 3 Pythons, mutation 22/22, fuzz, browser E2E. Minus coverage < 95% |
| Architecture and maintainability | 5 | 4.5 | Layered, stdlib only, documented decisions |
| User experience and accessibility | 5 | 4.0 | Automated UEUIS checks pass; no manual screen-reader pass |
| Performance and resource efficiency | 5 | 4.0 | Measured; no network-controlled profiling |
| Installation, documentation and operations | 5 | 4.5 | CI live, migration guide, changelog, clear failures on unsupported platforms |
| **Total** | **100** | **85.5** | |

**Final rating: 8.6 / 10.** It was 7.1 at the start of the programme and 7.6 for 2.0.0. It is **not 9.8**.
- No hard cap applies.
- The "meaningful end-to-end validation" cap is lifted by the verified real build.

**Why 9.8 is not claimed:** the rubric needs evidence that does not exist yet:
- independent human relevance labels;
- measured product value;
- an independent security review;
- separated install and execution phases;
- core coverage of 95% or more.

These cannot be produced honestly in this session. Inflating the score would break the programme's own rule.

## Next steps that would move the score most
1. Run the A/B value benchmark (paid; `tools/value_benchmark.py --i-accept-cost`).
2. Get human relevance labels for 30+ queries across GitHub, npm and plugins.
3. Run a two-phase build: a dependency-install phase with registry egress, then an execution phase with no network.
4. Raise core coverage to 95%.
5. Commission an external security review.
