# Final audit (Phase 12) — ReuseFirst 2.0.0

**Audited:** 2026-11-06. Start commit `76d9cb2` (1.13.0). End: `main` after merge `93388c7` and the README commit.

**Method:** the modified source was re-opened and each claim below was checked against code and a test or
measurement run in this session. Where something was not run, it says **NOT VERIFIED**. The rubric and caps are
the programme's own, unchanged.

## Evidence summary
| Check | Command | Result |
|---|---|---|
| Unit, integration, security, sandbox, fuzz, E2E-with-fakes | `python3 -m unittest discover -s tests` | **188 tests OK** (29.5 s) |
| Coverage (branch) | `coverage run …; coverage report` | **90%** overall; **89%** for the critical core (sandbox, server, policy, lifecycle, gates, reuse, builder) |
| Lint | `ruff check .` (E,F,W,B,S,I,UP,SIM) | clean |
| Security static analysis | `bandit -r … -ll` | 0 Medium/High (4 annotated false positives) |
| Sandbox self-test | `sandbox.self_test()` | 13/13 probes pass on WSL2 |
| Mutation check | `python3 tools/mutate.py` | **16/16 killed** |
| Retrieval benchmark | `python3 tests/benchmark/run_benchmark.py` | NDCG@10 0.740 → **0.763**, P@5 0.717 → 0.750, R@10 0.724 → 0.771, MRR 0.917 → 0.958 |
| Browser E2E (Chromium, light + dark, 390 px and 320 px, forced colours, keyboard) | `tests/e2e_browser.py` | PASS against a 2.0 server with the real catalog and real GitHub |
| Plugin manifest validation | pre-push hook (`claude plugin validate`) | passed (warning: no icon) |
| Live install | `claude plugin update`, restarted 5057 | 2.0.0 running; `sandbox_ok: true`; 403 without the token, 200 with it; token file 0600 |
| Real Claude inside the sandbox | one `claude -p` (no tools) | succeeded; egress log shows only api.anthropic.com allowed |
| Real end-to-end build with real Claude in the 2.0 sandbox | — | **NOT VERIFIED** (spends usage; awaiting approval) |
| GitHub Actions CI | — | **NOT VERIFIED**: the push of `.github/workflows/ci.yml` was refused because the gh token lacks the `workflow` scope |
| Firefox / WebKit | — | **NOT VERIFIED** (Chromium only) |
| Product value A/B (with vs without ReuseFirst) | `tools/value_benchmark.py` | harness ready; **live runs PENDING** (paid) |

## Findings from the baseline audit
All 22 findings were addressed in code, each with a regression test (docs/AUDIT_BASELINE.md):
- Critical: A1 and A2, unsandboxed builds and launch.
- High: A3, A4, A6, A7, A8, A10 and A11 (auth, parser DoS, NaN/inf, URL smuggling, unsafe pre-selection,
  self-certification, in-place enhancement).
- Medium and low: the rest.

One more defect was found during 2.0 and fixed: a Python 3.11 syntax error from an f-string that reused its own
quote character, present since 1.x.

## Remaining limitations (honest)
1. **Credential in the build sandbox.** Claude's credential file is mounted read-only into the build agent's
   sandbox, so generated code run during the build could read it. Egress is limited to four hosts, and the secret
   scan fails builds that leave tokens in files. **Severity: medium.**
2. **Token from `/api/session`.** Without `REQAN_STRICT_TOKEN=1`, another local OS user could fetch the session
   token with forged headers. **Low** on the single-user WSL target.
3. **Dependency installs share the build phase.** The agent's dependency installs (pip/npm to the registries) happen
   in the same phase as running untrusted code. Installation is not separated from execution.
4. **Discovery is lexical.** There is no semantic model. Scores are uncalibrated and the benchmark labels were made
   by the assistant, not independent humans (12 queries, plugin corpus only). Ranking for GitHub, npm and crates.io
   is not benchmarked.
5. **Real builds not re-verified.** No real end-to-end build ran on the 2.0 pipeline. The pipeline is verified with
   a fake Claude CLI and real bubblewrap.
6. **Coverage short of target.** Coverage is 90% (89% critical core) against the programme's 95% statement / 90%
   branch target for the core. Branch coverage of the high-risk controls is not at 100%. Server error paths and
   sandbox resource fallbacks are the main gaps.
7. **JavaScript not checked.** JS/TS syntax is NOT VERIFIED by the gates (no Node on the verifier).
8. **Platforms.** Native Windows and macOS are unsupported, and fail clearly.

## Score (programme rubric)
| Category | Weight | Score | Basis |
|---|---:|---:|---|
| Security and supply-chain safety | 20 | 16.0 | Real, tested isolation that fails closed; API auth; validation; licence policy; SBOM/OSV. Minus limitations 1–3; no independent pen test |
| Functional correctness and reliability | 15 | 12.0 | State machine, transactional enhancement, recovery, idempotency, cancel races, all tested. Minus no real-build run |
| Discovery and matching intelligence | 15 | 9.0 | Multi-provider, README evidence, decision engine, measured gain. Minus lexical only, uncalibrated, weak labels |
| Autonomous build quality | 15 | 11.0 | Independent gates decide success. Minus no real 2.0 build, JS unchecked, install/exec not separated |
| Testing and independent verification | 15 | 11.5 | 188 tests, fuzz/property, mutation 16/16, browser E2E. Minus coverage < 95%, CI not yet run remotely, Chromium only |
| Architecture and maintainability | 5 | 4.5 | Layered, stdlib only, documented decisions |
| User experience and accessibility | 5 | 4.0 | UEUIS checks pass in the automated E2E; no manual screen-reader pass (automated checks are not full WCAG conformance) |
| Performance and resource efficiency | 5 | 4.0 | Measured (44 ms offline analysis, 0.07 s sandbox overhead); no network-controlled profiling |
| Installation, documentation and operations | 5 | 4.0 | Complete docs, migration guide, changelog, fails clearly when unsupported; CI pending |
| **Total** | **100** | **76.0** | |

**Final rating: 7.6 / 10.** This is up from the programme's 7.1 starting assessment. It is **not** 9.8. No hard
cap applies below this score:
- no unresolved critical security issue;
- no unsafe fallback;
- no critical data-loss defect;
- success requires independent verification;
- tests are reproducible;
- retrieval is measured.

The "meaningful end-to-end" cap (9.0) would apply until a real build is verified.

**Not claimed:** production readiness or certification. That needs an independent security review and real-world
reliability data.

## What would move the score most
- Run a real sandboxed build (needs approval) and the A/B value benchmark (needs approval).
- Get independent human relevance labels across GitHub and npm queries.
- Add an optional local semantic re-ranker.
- Separate dependency installation from code execution (two sandboxed phases).
- Proxy the Claude API from outside the sandbox so the credential never enters it.
- Raise core coverage to 95%.
- Grant the `workflow` scope so CI runs on GitHub.
